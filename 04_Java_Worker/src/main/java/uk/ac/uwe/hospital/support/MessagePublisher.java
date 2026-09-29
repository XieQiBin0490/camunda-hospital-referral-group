package uk.ac.uwe.hospital.support;

import io.camunda.zeebe.client.ZeebeClient;
import io.camunda.zeebe.client.api.response.PublishMessageResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Publishes a Camunda 8 message so that a token waiting in <em>another</em> pool
 * can be correlated - the runtime half of the cross-pool message interaction the
 * models draw.
 *
 * <p>In Camunda 8 a message flow on the diagram is documentation only. Nothing
 * crosses a pool boundary unless somebody publishes a message, and a message
 * intermediate throw event is executed as a <em>job</em>: the engine creates it
 * and waits for a job worker to do the publishing. That is this class.
 *
 * <p>Two rules make it safe to call from inside a job handler:
 * <ul>
 *   <li>It never throws. Publishing is a notification to a different pool, which
 *       may not be deployed or may already have finished; that is not a reason to
 *       fail the job that is doing useful work. A failure is logged and reported
 *       as a negative message key.</li>
 *   <li>It never sends an empty correlation key by accident. Camunda 8 treats an
 *       empty key on a message start event as "no de-duplication", so a blank key
 *       silently creates a duplicate instance instead of correlating.</li>
 * </ul>
 *
 * <p>The client is attached once at start-up by
 * {@link uk.ac.uwe.hospital.WorkersApplication}. When no client is attached the
 * class is a logged no-op, which is what lets the unit tests exercise the
 * workers without a running engine.
 *
 * <p>中文：本类负责“跨池消息”里真正把消息发出去的那一半。Camunda 8 中画在协作图上的
 * 消息流只是文档，只有真的有人 publish 消息，令牌才能跨过池的边界；而消息抛出事件在
 * 引擎里就是一个作业，必须有工作器替它发布。这个类就是这个工作器背后的发布逻辑。
 *
 * <p>中文：它对作业处理者有两个安全承诺。第一，绝不抛异常：另一个池可能根本没部署或者
 * 早已结束，那不该让手上正在做正事的工作器失败，失败只记日志并返回负的消息键。
 * 第二，绝不误发空关联键：Camunda 8 把消息启动事件上的空关联键理解为“不去重”，
 * 于是会静默地多起一个实例，而不是关联到等待中的那一个。
 *
 * <p>中文：客户端在启动时由 WorkersApplication 注入一次；没有注入时本类退化为只记日志
 * 的空操作，单元测试因此可以在没有引擎的情况下照样跑通。
 */
public final class MessagePublisher {

    private static final Logger log = LoggerFactory.getLogger(MessagePublisher.class);

    /** 中文：启动时注入的引擎客户端；为空表示当前处于无引擎的单元测试模式。 */
    private static volatile ZeebeClient client;

    /** 中文：成功发出的消息条数，供关闭时汇总与核对跨池交互是否真的发生。 */
    private static final AtomicLong PUBLISHED = new AtomicLong();

    /** 中文：发布失败（含无客户端）的次数，与成功分开统计，避免把空操作当成成功。 */
    private static final AtomicLong FAILED = new AtomicLong();

    /** 中文：工具类不需要实例，私有构造器用于阻止实例化。 */
    private MessagePublisher() {
    }

    /** 中文：启动时注入引擎客户端；必须在工作器开始订阅之前调用。 */
    public static void use(ZeebeClient zeebeClient) {
        client = zeebeClient;
    }

    /** 中文：解除客户端绑定并清零计数，供单元测试在用例之间复位，避免相互影响。 */
    public static void reset() {
        client = null;
        PUBLISHED.set(0);
        FAILED.set(0);
    }

    /**
     * Publish one message and return its message key, or {@code -1} when it was
     * not published.
     *
     * <p>Note what the broker does <em>not</em> tell us: the publish API returns
     * the key it minted, not how many subscriptions correlated with it. A message
     * nobody is waiting for is accepted and dropped. That is why the callers
     * record the key rather than a boolean "delivered" flag - the key proves the
     * message was published, and the receiving side's own record proves it was
     * consumed.
     *
     * <p>中文：发布一条消息并返回消息键；未发布时返回 -1。需要特别说明的是，发布接口只
     * 返回引擎生成的消息键，并不会告诉我们有多少个订阅者关联成功；没有人在等的消息会被
     * 正常接收后丢弃。因此调用方记录的是“消息键”而不是一个“已送达”的布尔值：
     * 消息键只能证明消息确实发出，真正被消费要由接收方的记录来证明。
     *
     * @param messageName    the BPMN message name, which must match the catch or
     *                       start event on the other side exactly
     * @param correlationKey the value the receiving side's {@code correlationKey}
     *                       expression evaluates to; blank falls back to
     *                       {@code fallbackKey}, and a still-blank key is refused
     * @param variables      the message payload, merged into the receiving
     *                       instance's variables
     */
    public static long publish(String messageName, String correlationKey,
                               String fallbackKey, Map<String, Object> variables) {
        // 中文：消息名是接收方订阅的唯一依据，为空说明调用方写错了，属于编码缺陷，直接拒绝。
        if (messageName == null || messageName.isBlank()) {
            throw new IllegalArgumentException("a message name is required to publish a message");
        }
        // 中文：关联键为空时先退回到调用方给的兜底键，再为空才真正拒绝，避免静默制造重复实例。
        String key = correlationKey == null || correlationKey.isBlank() ? fallbackKey : correlationKey;
        if (key == null || key.isBlank()) {
            log.warn("refusing to publish message '{}': no correlation key is available, and an "
                    + "empty key would create a duplicate instance rather than correlate", messageName);
            FAILED.incrementAndGet();
            return -1L;
        }
        // 中文：无客户端即单元测试模式，记录后按未发布返回，不抛异常也不计为成功。
        if (client == null) {
            log.info("message '{}' (correlationKey={}) not published: no gateway client is attached",
                    messageName, key);
            return -1L;
        }
        Map<String, Object> payload = variables == null ? Map.of() : new LinkedHashMap<>(variables);
        try {
            PublishMessageResponse response = client.newPublishMessageCommand()
                    .messageName(messageName)
                    .correlationKey(key)
                    // 中文：同步等待引擎确认，保证返回时消息已经进入引擎，而不是仅仅写进了本地缓冲。
                    .variables(payload)
                    .send()
                    .join();
            PUBLISHED.incrementAndGet();
            log.info("published message '{}' key={} correlationKey={} payloadKeys={}",
                    messageName, response.getMessageKey(), key, payload.keySet());
            return response.getMessageKey();
        } catch (RuntimeException e) {
            // 中文：发布失败只降级为告警。跨池通知失败不应把正在推进业务流程的作业打成失败，
            // 中文：否则一个尚未部署的协作池会让主流程产生 incident。
            FAILED.incrementAndGet();
            log.warn("could not publish message '{}' (correlationKey={}): {}",
                    messageName, key, e.getMessage());
            return -1L;
        }
    }

    /** 中文：成功发布的消息总数，用于在关闭日志中确认跨池交互确实发生。 */
    public static long published() {
        return PUBLISHED.get();
    }

    /** 中文：发布失败或被拒绝的次数，正常演示中应保持为 0。 */
    public static long failed() {
        return FAILED.get();
    }
}

package uk.ac.uwe.hospital.support;

import uk.ac.uwe.hospital.BpmnErrorException;
import uk.ac.uwe.hospital.TransientJobException;
import uk.ac.uwe.hospital.WorkerConfig;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Deterministic fault injection, so the failure paths can be demonstrated on
 * demand instead of being described.
 *
 * <p>Three modes, chosen by {@code failure.mode}:
 * <ul>
 *   <li>{@code off}   - nothing is injected (the normal run);</li>
 *   <li>{@code rules} - job types named in {@code failure.prefix} fail once, which
 *       drives the engine's retry policy: the job is failed with one fewer retry
 *       and succeeds on the second activation;</li>
 *   <li>{@code all}   - every automated activity fails once.</li>
 * </ul>
 * A job type may carry an explicit error code as {@code job-type:ERROR_CODE},
 * which is thrown as a BPMN error rather than failed, so the boundary event on
 * the model - where one exists - is what handles it.
 *
 * <p>中文：这里的故障注入是确定性的，目的是让容错分支可被真实触发，而不是只写在文档里。
 * 三种模式区别明确：关闭时完全不影响正常路径；规则模式只让点名的工作类型失败一次，
 * 从而驱动引擎的失败重试机制；全量模式则让所有自动活动都失败一次。带冒号的写法把
 * BPMN 错误码一并写在规则里，此时抛出的是业务错误而非可重试失败，交由模型上的边界事件
 * 处理，因为二者的流程语义完全不同：前者可重试，后者必须走补偿或异常分支。
 */
public final class FailureInjection {

    /** 中文：已注入过故障的工作类型集合，保证同一类型只失败一次，重试才有成功的机会。 */
    private static final Set<String> ONCE = ConcurrentHashMap.newKeySet();
    /** 中文：按工作类型统计实际注入次数，供观测与测试断言使用，便于证明故障确实发生过。 */
    private static final Map<String, AtomicInteger> COUNTS = new ConcurrentHashMap<>();
    /** 中文：声明为 volatile，使运行时切换的故障模式能立刻被各工作线程看到，无需重启进程。 */
    private static volatile WorkerConfig config;

    /** 中文：工具类不需要实例，私有构造器用于阻止外部创建对象。 */
    private FailureInjection() {
    }

    /** 中文：注入配置来源，通常由外部工作者启动时调用；只保存引用，不复制内容。 */
    public static void configure(WorkerConfig cfg) {
        config = cfg;
    }

    /** 中文：判定是否启用注入。未配置时视为关闭，使默认部署不会意外触发任何故障。 */
    public static boolean enabled() {
        return config != null && !"off".equalsIgnoreCase(config.failureMode());
    }

    /**
     * 中文：每次激活工作项前调用。规则文本中冒号之后的部分是 BPMN 错误码；ONCE 集合的
     * add 操作具有原子性，可用它来保证同一工作类型只失败一次，这样“失败后重试成功”的
     * 路径才能被稳定观察到，而不会陷入无限失败。并发下也只有第一个调用者会继续抛错。
     */
    public static void check(String jobType) {
        if (!enabled()) {
            return;
        }
        String spec = rule(jobType);
        if (spec == null) {
            return;
        }
        String code = "";
        // 中文：冒号必须出现在位置 0 之后，否则规则本身没有工作类型，属于无效配置，直接忽略。
        int colon = spec.indexOf(':');
        if (colon > 0) {
            code = spec.substring(colon + 1).trim();
        }
        if (!ONCE.add(jobType)) {
            // the fault fires once per job type, so the retry can be seen to work
            return;
        }
        COUNTS.computeIfAbsent(jobType, k -> new AtomicInteger()).incrementAndGet();
        // 中文：区分两种语义——无可重试的临时失败会消耗一次重试机会，BPMN 错误则立即转入异常分支。
        if (code.isEmpty()) {
            throw new TransientJobException("injected transient failure for job type " + jobType);
        }
        throw new BpmnErrorException(code, "injected business error " + code + " for job type " + jobType);
    }

    /** 中文：根据模式与规则列表判定该工作类型是否命中注入；全量模式直接命中，无需配置列表。 */
    private static String rule(String jobType) {
        String mode = config.failureMode();
        if ("all".equalsIgnoreCase(mode)) {
            return jobType;
        }
        String list = config.failurePrefix();
        if (list == null || list.isBlank()) {
            return null;
        }
        return Arrays.stream(list.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .filter(s -> s.equals(jobType) || s.equals(jobType + ":") || s.startsWith(jobType + ":"))
                .findFirst()
                .orElse(null);
    }

    /** 中文：清空“已注入”标记与计数，使同一进程内的演示可以重复播放同一组故障。 */
    public static void reset() {
        ONCE.clear();
        COUNTS.clear();
    }
}

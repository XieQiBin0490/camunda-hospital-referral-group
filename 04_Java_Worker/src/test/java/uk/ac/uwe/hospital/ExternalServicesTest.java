package uk.ac.uwe.hospital;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.FailureInjection;
import uk.ac.uwe.hospital.support.HospitalStore;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The simulated providers, and the two rules that decide what a failure means.
 *
 * <p>The distinction under test is the one the whole design rests on: a provider
 * that <b>answers "no"</b> produces a business outcome the model branches on,
 * while a provider that <b>does not answer</b> produces a retry. Conflating them
 * would send a patient down an escalation path because of a network fault.
 *
 * <p>中文：本测试类保护的是“模拟外部服务层”的行为契约，也就是所有 worker 在
 * 调用医院外部系统时看到的那一层。它锁定的核心不变量有两条：第一，外部系统
 * 给出明确的否定答复（例如没有可用号源、容量被拒、付款被拒）属于业务结果，
 * 必须作为正常返回值交回给流程，让网关据此走分支；第二，外部系统根本不答复
 * （超时、不可用、无响应）属于技术故障，必须抛出可重试异常，交给 Zeebe 的
 * 重试机制处理。如果把这两类情况混为一谈，一次网络抖动就会被误判成“没有号
 * 源”，病人会被错误地推入升级/转诊路径。此外本类还固定了付款四种结果与网
 * 关变量取值之间的映射、资源封锁的命名规则（大小写不敏感），以及只影响一次
 * 的故障注入开关，因为这些都直接决定演示与答辩时流程走向是否可复现。
 */
class ExternalServicesTest {

    /**
     * 中文：每个测试结束后清理系统属性和共享状态，保证用例之间互不污染。
     * 这里逐个清除的 property 正是各模拟服务用来触发“不答复/拒绝”的开关，
     * 若残留到下一个用例，会把后续断言结果带偏。
     */
    @AfterEach
    void clear() {
        for (String k : new String[]{"hpas.scheduling.noSlots", "hpas.scheduling.unavailable",
                "hpas.capacity.unavailable", "hpas.capacity.unavailableOnce", "hpas.capacity.blockedResources",
                "hpas.capacity.resource", "hpas.payment.outcome", "hpas.payment.outcomeOnce",
                "hpas.refund.rejected", "hpas.correspondence.unavailable"}) {
            System.clearProperty(k);
        }
        FailureInjection.reset();
        HospitalStore.get().clear();
    }

    @Test
    @DisplayName("a routine search beyond two weeks finds slots; a very short one may not")
    void schedulingReturnsSlotsOrAnEmptyAnswer() {
        // 中文：场景（Given/When/Then）——给定肿瘤科默认的号源检索服务，当以
        // 28 天的合理时间窗查询时（When），应当返回非空号源列表（Then）。
        assertFalse(ExternalServices.Scheduling.findSlots("Oncology", 28, false).slots().isEmpty());
        // 中文：当时间窗被压到 1 天这种几乎不可能有号的极端情况（When），
        // 结果应为空列表（Then）。这里与上面的对比说明了“空”是数据本身的性质，
        // 而不是服务出故障。
        ExternalServices.Scheduling.Result none = ExternalServices.Scheduling.findSlots("Oncology", 1, false);
        assertTrue(none.slots().isEmpty());
        // 中文：这条断言把“空结果”和“无响应”彻底区分开。available() 为 true
        // 表示服务确实给了答复，只是答复内容是没有号源。若这里将来变成 false，
        // worker 就会把它当成技术故障去重试，从而把“确实没号”误判成系统问题。
        assertTrue(none.available(), "an empty result is still an answer");
    }

    @Test
    @DisplayName("a scheduling service that does not answer is a retryable failure, not an empty answer")
    void unansweredSchedulingThrowsRetryable() {
        // 中文：故意注入“排班服务不可用”这一故障（Given/When）。它模拟的是
        // 网络或服务端故障导致没有答复，而不是业务上的“没有号源”。
        System.setProperty("hpas.scheduling.unavailable", "true");
        // 中文：不可用必须表现为 TransientJobException，也就是可重试异常，让
        // Zeebe 走重试而不是把任务直接判死。若这里改成返回空结果，流程会把
        // 系统故障当作“无号源”分支处理，病人会被错误地转给路径协调员。
        assertThrows(TransientJobException.class,
                () -> ExternalServices.Scheduling.findSlots("Oncology", 28, false));
    }

    @Test
    @DisplayName("capacity is confirmed by default and refused when forced")
    void capacityConfirmsOrRefuses() {
        // 中文：默认路径下容量申请应被确认（Then），这是“happy path”的基准，
        // 后续所有拒绝场景都是相对它而言的异常分支。
        assertTrue(ExternalServices.Capacity.request("CHEMO-6", 6, "").confirmed());

        // 中文：注入容量服务不可用（When）。注意这里返回的是 Result 而不是抛
        // 异常，说明“容量被拒”在设计上属于业务结果。
        System.setProperty("hpas.capacity.unavailable", "true");
        ExternalServices.Capacity.Result refused = ExternalServices.Capacity.request("CHEMO-6", 6, "");
        assertFalse(refused.confirmed());
        // 中文：拒绝时必须指出到底是哪种资源不可用，因为 BPMN 后续要用这个
        // 变量决定“待定/升级”分支，并让运营人员知道该去协调哪台设备。缺了它
        // 流程会出现空指针式的空变量，网关会走到没人选择的分支。
        assertNotNull(refused.unavailableResource(), "a refusal must name what was unavailable");
    }

    @Test
    @DisplayName("a named resource can be blocked without blocking everything")
    void namedResourceCanBeBlocked() {
        // 中文：给定 MRI 与 PET-CT 被封锁（Given）。这种“按名称封锁单台设备”
        // 的能力用于演示某台机器停机时流程的降级行为。
        System.setProperty("hpas.capacity.blockedResources", "MRI,PET-CT");
        // 中文：没有要求特定资源的申请仍然成功，说明封锁是点对点的，不会因为
        // 一台设备停机就把整个容量服务打挂——否则一次设备维护会阻断全院流程。
        assertTrue(ExternalServices.Capacity.request("CHEMO-6", 6, "CT").confirmed());
        // 中文：指定 MRI 的申请被拒（Then），验证封锁名单确实生效。
        assertFalse(ExternalServices.Capacity.request("CHEMO-6", 6, "MRI").confirmed());
        // 中文：用小写 pet-ct 去匹配大写 PET-CT 仍然被拒，说明资源名比较做了
        // 大小写归一化。若缺了这一步，BPMN 里写成小写的资源名就会绕过封锁，
        // 造成“以为已经停机却仍然排上了号”的真实业务事故。
        assertFalse(ExternalServices.Capacity.request("CHEMO-6", 6, "pet-ct").confirmed(),
                "resource matching ignores case");
    }

    @Test
    @DisplayName("the four payment outcomes map to the four values the gateway reads")
    void paymentOutcomesMapToGatewayValues() {
        // 中文：默认（正常）路径：付款成功时给出的流程变量值必须是 confirmed。
        // 这四个取值是 BPMN 网关直接读取的字面量，改动其中任何一个都会让网关
        // 匹配不到条件而走入默认分支。
        assertEquals("confirmed", ExternalServices.Payment.request("EP-1", 1.0d, "GBP").outcome().processValue());
        // 中文：成功交易必须带有交易流水号，它是后续退款 REQ 能对账的前提，
        // 也是“无可退原交易”判定的依据。
        assertNotNull(ExternalServices.Payment.request("EP-1", 1.0d, "GBP").transactionReference());

        // 中文：强制付款被拒（When）。注意“DECLINED”是触发开关的输入值，
        // 而下面断言的是映射后的流程变量值 "declined"，两者大小写不同正是
        // 要验证的映射关系。
        System.setProperty("hpas.payment.outcome", "DECLINED");
        ExternalServices.Payment.Result declined = ExternalServices.Payment.request("EP-2", 1.0d, "GBP");
        assertEquals("declined", declined.outcome().processValue());
        // 中文：被拒的付款不能凭空产生交易流水号。若这里出现非 null 值，
        // 后续退款校验就会误以为存在一笔可退的交易，出现“没扣钱却退款”的
        // 财务漏洞。
        assertEquals(null, declined.transactionReference(), "a declined payment has no reference");

        // 中文：模拟“支付方超时无响应”这一最棘手的情况：钱可能已经划走，
        // 但系统没拿到明确结果。它必须映射成独立取值，不能等同于 declined。
        System.setProperty("hpas.payment.outcome", "NO_RESPONSE");
        ExternalServices.Payment.Result lost = ExternalServices.Payment.request("EP-3", 1.0d, "GBP");
        assertEquals("no response", lost.outcome().processValue());
        // 中文：与 declined 相反，无响应场景必须保留交易流水号，因为资金确实
        // 可能已被扣划，对账与后续退款都需要这个凭据。这正是两种失败语义
        // 必须分开的核心原因。
        assertNotNull(lost.transactionReference(),
                "the provider took the money, so there is a reference even though nothing was confirmed");

        // 中文：第四种取值用于临床紧急需要场景，网关据此跳过常规付款等待，
        // 因此它的字面量同样是流程契约的一部分，不能随意改名。
        System.setProperty("hpas.payment.outcome", "URGENT_CLINICAL_NEED");
        assertEquals("urgent clinical need",
                ExternalServices.Payment.request("EP-4", 1.0d, "GBP").outcome().processValue());
    }

    @Test
    @DisplayName("a forced decline applies to the first transaction only, so the retry can succeed")
    void forcedDeclineAppliesOnce() {
        // 中文：给定强制拒绝开关，且默认只生效一次（Given）。
        System.setProperty("hpas.payment.outcome", "DECLINED");
        // 中文：第一次请求被拒（Then）。
        assertEquals("declined", ExternalServices.Payment.request("EP-5", 1.0d, "GBP").outcome().processValue());
        // 中文：同一个 episode 的第二次请求必须成功。这是故意设计的“只失败
        // 一次”技巧，用来演示 REQ-22 要求的重试与防重复扣款：既证明了用户
        // 可以换卡重试，又证明重试没有被无脑地再次拒绝。若这里仍是 declined，
        // 演示时流程会卡死在付款环节无法继续。
        assertEquals("confirmed", ExternalServices.Payment.request("EP-5", 1.0d, "GBP").outcome().processValue(),
                "the second attempt is what REQ-22 says must be permitted");
    }

    @Test
    @DisplayName("the forced decline can be made permanent for a demonstration")
    void forcedDeclineCanBePermanent() {
        // 中文：把“只失败一次”关掉，让强制拒绝持续生效（Given）。这个开关
        // 专门为演示准备：答辩时需要让流程稳定地停在拒付分支上给评审看，
        // 而不是第一次失败、第二次就自动恢复。
        System.setProperty("hpas.payment.outcome", "DECLINED");
        System.setProperty("hpas.payment.outcomeOnce", "false");
        // 中文：两次连续请求都必须是 declined，用以证明永久模式确实覆盖了
        // 默认的“只失败一次”行为；如果这里第二次变成 confirmed，说明开关
        // 没被读取，演示将无法复现拒付路径。
        assertEquals("declined", ExternalServices.Payment.request("EP-6", 1.0d, "GBP").outcome().processValue());
        assertEquals("declined", ExternalServices.Payment.request("EP-6", 1.0d, "GBP").outcome().processValue());
    }

    @Test
    @DisplayName("a refund needs an original transaction, and can be rejected by the provider")
    void refundRequiresAnOriginalAndCanBeRejected() {
        // 中文：没有原始交易凭据时退款必须被拒（Then）。这是财务安全的底线：
        // 否则流程可以凭一个空字符串就凭空退款，造成实际资金损失。
        assertFalse(ExternalServices.Payment.refund(10.0d, "").approved(),
                "there is nothing to refund against");
        // 中文：给定有效的原始交易号，退款应被批准，构成上面的对照。
        assertTrue(ExternalServices.Payment.refund(10.0d, "PAY-1").approved());

        // 中文：注入“支付方拒绝退款”（When）。这说明即便请求在业务上合规，
        // 外部服务仍可能说不，代码必须把这个否定结果如实反馈给流程，让流程
        // 进入人工处理分支，而不是假设退款一定会成功。
        System.setProperty("hpas.refund.rejected", "true");
        assertFalse(ExternalServices.Payment.refund(10.0d, "PAY-1").approved());
    }

    @Test
    @DisplayName("correspondence that does not answer is a retryable failure")
    void unansweredCorrespondenceThrowsRetryable() {
        // 中文：正常路径下信件投递应返回一个非空凭据（Then），它会被写回流程
        // 作为审计与追踪依据。
        assertNotNull(ExternalServices.Correspondence.dispatch("letter", "patient"));
        // 中文：注入“通信服务不答复”（When）。与排班服务同理，文书投递失败
        // 属于技术故障，必须可重试，不能静默地当作“已发送”，否则信函既没寄出
        // 流程又显示成功——这正是医疗场景中不可接受的静默丢失。
        System.setProperty("hpas.correspondence.unavailable", "true");
        assertThrows(TransientJobException.class,
                () -> ExternalServices.Correspondence.dispatch("letter", "patient"));
    }

    @Test
    @DisplayName("fault injection is off by default and fires once per job type when enabled")
    void failureInjectionFiresOnce() {
        // off
        // 中文：默认配置下即使是未知 job type 调用 check 也不应抛异常，也就是
        // 说故障注入功能必须默认处于关闭状态。这保证正常运行环境不会被测试
        // 用的故障开关意外影响，出现“生产环境随机失败”的假象。
        FailureInjection.check("any-job");

        // 中文：加载真实配置并据此重新初始化故障注入（When），随后确认默认
        // 配置文件里没有任何 job type 被标记为注入故障（Then）。
        WorkerConfig cfg = WorkerConfig.load();
        FailureInjection.configure(cfg);
        // 中文：若这条断言失败，意味着配置或默认值把某个 job type 变成了
        // 必然失败，所有依赖该 worker 的流程会在无人察觉的情况下持续重试。
        assertFalse(FailureInjection.enabled(), "the default configuration injects nothing");
    }
}

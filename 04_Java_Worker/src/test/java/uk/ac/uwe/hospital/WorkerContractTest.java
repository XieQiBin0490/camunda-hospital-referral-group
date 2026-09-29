package uk.ac.uwe.hospital;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import uk.ac.uwe.hospital.support.FailureInjection;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.OperationsLog;
import uk.ac.uwe.hospital.tasks.DistributeClinicalCorrespondenceWorker;
import uk.ac.uwe.hospital.tasks.GenerateManagementReportsWorker;
import uk.ac.uwe.hospital.tasks.PublishPatientReferralWorker;
import uk.ac.uwe.hospital.tasks.QueryAvailableAppointmentSlotsWorker;
import uk.ac.uwe.hospital.tasks.RedirectReferralWorker;
import uk.ac.uwe.hospital.tasks.RequestBloodTestWorker;
import uk.ac.uwe.hospital.tasks.RequestMissingDocumentationWorker;
import uk.ac.uwe.hospital.tasks.RequestRefundWorker;
import uk.ac.uwe.hospital.tasks.RequestSecurePaymentWorker;
import uk.ac.uwe.hospital.tasks.RequestTreatmentCapacityWorker;
import uk.ac.uwe.hospital.tasks.SendAppointmentConfirmationLetterWorker;
import uk.ac.uwe.hospital.tasks.SendReferralOutcomeWorker;
import uk.ac.uwe.hospital.tasks.SubmitPatientReferralWorker;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The variable-to-branch contract, one test per worker.
 *
 * <p>This is the suite that earns its keep. A model review cannot tell you
 * whether {@code request-treatment-capacity} really writes
 * {@code treatmentCapacityConfirmed}, and neither can a lint run; only the live
 * engine or these tests can. Three of the eleven workers own a variable a
 * gateway reads, and those three are the ones tested hardest.
 *
 * <p>中文：本测试类保护的是“BPMN 流程与外部 worker 之间的变量契约”，每个 worker
 * 一个用例。它锁定的核心不变量是：worker 必须把自己负责的流程变量以正确的名字
 * 与取值写回流程，因为排他网关正是靠这些变量的字面量来选择分支。尤其是那三个
 * “网关变量”——suitableSlotFound、treatmentCapacityConfirmed 和 paymentStatus——
 * 它们直接决定病人是继续治疗、进入待定升级还是被判为付款失败。静态检查模型或
 * 人工评审都无法证明某个 job type 真的写入了某个变量名，只有真正执行 worker
 * 才能验证，因此这个套件是不可替代的。除网关变量外，本类还固定了防重复预约、
 * 防重复扣款（REQ-22）、不把银行卡数据写回流程（REQ-21）以及各个 job type 名称
 * 与模型声明一致等关键业务规则。
 */
class WorkerContractTest {

    /**
     * 中文：每个用例后清理系统属性、共享存储、审计日志与故障注入状态。这些
     * 都是静态共享的单例，若不清空，前一个用例注入的故障或写入的记录会污染
     * 后一个用例的断言。
     */
    @AfterEach
    void reset() {
        for (String k : new String[]{"hpas.scheduling.noSlots", "hpas.capacity.unavailableOnce",
                "hpas.capacity.unavailable", "hpas.payment.outcome", "hpas.refund.rejected",
                "hpas.correspondence.unavailable"}) {
            System.clearProperty(k);
        }
        HospitalStore.get().clear();
        OperationsLog.get().clear();
        FailureInjection.reset();
    }

    /**
     * 中文：测试辅助方法，模拟 Zeebe 执行一次作业：用给定变量构造 JobContext，
     * 调用 worker.handle，然后返回它写回的变量集。这样每个用例只需准备输入变量
     * 并断言输出变量，等价于在真实引擎里跑一次该服务任务。
     */
    private static Map<String, Object> run(AbstractWorker worker, Map<String, Object> vars) {
        JobContext ctx = new JobContext(worker.jobType(), 1L, 2L, "T_Test", 3, vars);
        worker.handle(ctx);
        return ctx.outputs();
    }

    /**
     * 中文：测试辅助方法，用 key/value 交替的可变参数快速拼出变量表。写成
     * kv[i]、kv[i+1] 这种成对取值，是为了让用例里“变量名, 值”紧挨着出现，
     * 便于对照 BPMN 模型逐个核对变量名是否拼写正确。
     */
    private static Map<String, Object> vars(Object... kv) {
        Map<String, Object> m = new HashMap<>();
        for (int i = 0; i < kv.length; i += 2) {
            m.put(String.valueOf(kv[i]), kv[i + 1]);
        }
        return m;
    }

    // ------------------------------------------------- the three gating workers
    // 中文：以下三个 worker 各自拥有一个被排他网关直接读取的变量，是整套流程
    // 最容易出错、也最必须覆盖的部分，因此测试最密集。

    @Test
    @DisplayName("query-available-appointment-slots owns suitableSlotFound: true when slots exist")
    void slotsFoundSetsTheGatewayVariable() {
        // 中文：场景（Given/When/Then）——给定一个肿瘤科、时间窗 28 天的转诊
        // 查询（Given），当排班 worker 执行时（When），应当把网关变量
        // suitableSlotFound 置为 true（Then），流程才能走向真正的预约分支。
        Map<String, Object> out = run(new QueryAvailableAppointmentSlotsWorker(),
                vars("patientId", "P-1", "requestedSpeciality", "Oncology", "preferredTimeframeDays", 28));
        // 中文：true 必须同时写入 schedulingServiceAnswered，用来区分“服务答了
        // 且有号”与“服务答了但没号”。网关只读 suitableSlotFound，而运维排查时
        // 需要靠这个变量判断到底是没号还是没联系上。
        assertEquals(true, out.get("suitableSlotFound"));
        assertEquals(true, out.get("schedulingServiceAnswered"));
        // 中文：号源数量必须大于 0 而不是仅仅“存在”。若数量为 0 却把网关变量置为
        // true，流程会进入预约环节却无号可约，出现业务流程与数据自相矛盾。
        assertTrue((Integer) out.get("availableSlotCount") > 0);
        // 中文：必须写回排班引用号，它是后续预约确认与对账时指向本次查询结果的
        // 凭据；缺少它，预约环节就无从关联到具体是哪次检索。
        assertTrue(out.containsKey("schedulingReference"));
        // 中文：episodeId 是整条流程的关联键，所有后续 worker 都靠它归档数据。
        // 若这个 worker 漏写，后面按 episode 查询都会落空。
        assertTrue(out.containsKey("episodeId"));
    }

    @Test
    @DisplayName("query-available-appointment-slots owns suitableSlotFound: false when the service answers with none")
    void noSlotsClearsTheGatewayVariable() {
        // 中文：注入“没有可用号源”这一业务答复（Given/When）。注意这是明确的
        // 否定答复，不是服务故障，所以不应抛异常。
        System.setProperty("hpas.scheduling.noSlots", "true");
        Map<String, Object> out = run(new QueryAvailableAppointmentSlotsWorker(),
                vars("patientId", "P-1", "preferredTimeframeDays", 28));
        // 中文：网关变量必须是 false 而不是缺失。REQ-12 规定无号源时转交路径
        // 协调员；若变量缺失，Camunda 8 会把它求值为 null，网关条件都不成立而
        // 走默认分支，病人会被送进无人预期的路径。
        assertEquals(false, out.get("suitableSlotFound"), "REQ-12 routes this to the pathway coordinator");
        // 中文：数量应为 0，与 false 保持一致，避免下游出现“标记为无号但数量不为零”
        // 的矛盾数据。
        assertEquals(0, out.get("availableSlotCount"));
        // 中文：无号源时不应存在排班引用号——没有成功的检索就不该生成凭据，
        // 否则后续环节可能拿着一个空凭据去尝试预约。
        assertFalse(out.containsKey("schedulingReference"));
    }

    @Test
    @DisplayName("request-treatment-capacity owns treatmentCapacityConfirmed and never books twice")
    void capacityWorkerOwnsTheGatewayVariable() {
        // 中文：场景（Given/When/Then）——给定一个化疗 6 周期的容量申请（Given），
        // 当容量 worker 执行时（When），必须把 treatmentCapacityConfirmed 置为
        // true（Then），这是该 worker 对网关承担的核心义务。
        Map<String, Object> first = run(new RequestTreatmentCapacityWorker(),
                vars("patientId", "P-1", "episodeId", "EP-C", "treatmentCode", "CHEMO-6", "treatmentCycles", 6));
        assertEquals(true, first.get("treatmentCapacityConfirmed"));
        // 中文：首次尝试即成功时，尝试次数必须记为 1。这个计数是升级判断的基准，
        // 若首次就记成 0 或 2，后续“达到上限则升级”的逻辑会错判。
        assertEquals(1, first.get("capacityAttemptCount"));
        // 中文：首次成功时绝不能标记为创建了重复预约，否则流程会走异常/回滚分支，
        // 把一次正常预约当成故障处理。
        assertEquals(false, first.get("duplicateAppointmentCreated"));
        // 中文：必须写回容量引用号，它是后续确认与审计的依据，也是“到底有没有
        // 真的占住这台设备”的唯一凭据。
        assertTrue(first.containsKey("capacityReference"));
    }

    @Test
    @DisplayName("an unavailable service leaves the booking pending with an attempt count and a next date")
    void unavailableCapacityLeavesTheBookingPending() {
        // 中文：给定一个只会失败一次的容量服务故障，以及指定 MRI 的申请
        // （Given）。用“只失败一次”的技巧是为了在同一条 episode 上先观察失败
        // 结果的变量，再观察重试成功的变量，无需清理存储状态。
        System.setProperty("hpas.capacity.unavailableOnce", "true");
        RequestTreatmentCapacityWorker worker = new RequestTreatmentCapacityWorker();
        Map<String, Object> vars = vars("patientId", "P-1", "episodeId", "EP-P",
                "treatmentCode", "CHEMO-6", "treatmentCycles", 6, "requiredResource", "MRI");

        // 中文：第一次执行应把容量标记为未确认（Then），流程据此进入 REQ-16
        // 规定的待定分支，而不是把病人当成已排上号。
        Map<String, Object> refused = run(worker, vars);
        assertEquals(false, refused.get("treatmentCapacityConfirmed"),
                "REQ-16 routes this to the pending branch");
        // 中文：失败也要记录尝试次数，否则无法判断是否已经反复失败、是否该升级。
        assertEquals(1, refused.get("capacityAttemptCount"));
        // 中文：必须写回到底是 MRI 不可用，这样运营人员知道去协调哪台设备，
        // 也让人工处理环节有明确的对象。
        assertEquals("MRI", refused.get("unavailableResource"));
        // 中文：必须给出下次尝试日期，它是流程等待/定时重试的时间依据；缺失会
        // 导致待定分支无法安排后续动作。
        assertTrue(refused.containsKey("capacityNextAttemptDate"));
        // 中文：失败时不能标记重复预约，因为这一次根本没有生成预约。
        assertEquals(false, refused.get("duplicateAppointmentCreated"));
        // 中文：仅失败一次时还未触达尝试上限，因此升级标志必须是 false。这条
        // 断言防止实现把“任意一次失败”都当成需要人工升级，从而让待定分支
        // 失去意义。
        assertEquals(false, refused.get("capacityEscalationRequired"), "not yet at the attempt cap");

        // 中文：在同一 episode 上重试（When）。因为故障只注入一次，这次应成功。
        Map<String, Object> retried = run(worker, vars);
        // 中文：重试后网关变量必须翻转为 true，证明流程确实能自行恢复，
        // 而不是被一次瞬时故障永久卡死。
        assertEquals(true, retried.get("treatmentCapacityConfirmed"), "the retry succeeds");
        // 中文：尝试次数应累加到 2，证明计数器跨两次执行保留了状态（存在共享
        // 存储里），而不是每次调用都重置为 1——否则上限永远不会到达。
        assertEquals(2, retried.get("capacityAttemptCount"), "and the attempt is recorded");
        // 中文：重试成功后仍不得出现重复预约标记，确认整个重试过程只真正占用了
        // 一次资源，没有因为反复调用给同一台设备重复下单。
        assertEquals(false, retried.get("duplicateAppointmentCreated"));
    }

    @Test
    @DisplayName("request-secure-payment owns paymentStatus for each of the four outcomes")
    void paymentWorkerOwnsTheGatewayVariable() {
        // 中文：场景（Given/When/Then）——分别给定四种付款结果（Given），当
        // 付款 worker 执行后（When），paymentStatus 必须分别是网关约定的四个
        // 字面量（Then）。四个分支各覆盖一次，确保没有任何一种结果被漏映射或
        // 被误合并到别的分支。
        assertEquals("confirmed", statusFor("EP-1", null));
        assertEquals("declined", statusFor("EP-2", "DECLINED"));
        assertEquals("no response", statusFor("EP-3", "NO_RESPONSE"));
        assertEquals("urgent clinical need", statusFor("EP-4", "URGENT_CLINICAL_NEED"));
    }

    /**
     * 中文：测试辅助方法，按需注入付款结果后执行一次付款 worker，并返回它写入
     * 的 paymentStatus。方法内顺带断言 cardDataStored 为 false，从而保证每个
     * 付款场景都同时满足 REQ-21：无论结果如何，都不把卡数据标记为已存储。
     * forced 为 null 表示走默认的成功路径。
     */
    private String statusFor(String episode, String forced) {
        if (forced != null) {
            System.setProperty("hpas.payment.outcome", forced);
        }
        Map<String, Object> out = run(new RequestSecurePaymentWorker(),
                vars("patientId", "P-1", "episodeId", episode, "chargeAmount", 480.0d, "currency", "GBP"));
        System.clearProperty("hpas.payment.outcome");
        assertEquals(false, out.get("cardDataStored"));
        return String.valueOf(out.get("paymentStatus"));
    }

    @Test
    @DisplayName("no complete card data is ever read back or written to the process (REQ-21)")
    void noCardDataReachesTheProcess() {
        // 中文：给定完整可用的卡数据（Given），当付款 worker 执行时（When），
        // 一个字段都不允许出现在写回的变量里（Then）。这是 REQ-21 的合规底线：
        // 流程变量会进入 Zeebe 的持久化存储与操作日志，等于把卡号明文落库。
        Map<String, Object> out = run(new RequestSecurePaymentWorker(),
                vars("patientId", "P-1", "episodeId", "EP-CARD", "chargeAmount", 480.0d,
                        "cardNumber", "4111111111111111", "cvv", "123", "expiryDate", "12/28"));
        // 中文：逐个检查敏感字段名，包括 pan、securityCode 这类同义写法。用循环
        // 而不是逐条断言，是为了保证任何新增的敏感字段名都会被纳入同一道检查，
        // 而不是只挡住已经想到的那几个。
        for (String forbidden : new String[]{"cardNumber", "cvv", "expiryDate", "pan", "securityCode"}) {
            assertFalse(out.containsKey(forbidden), forbidden + " must not be written back");
        }
        // 中文：同时必须把 cardDataStored 明确置为 false。只“不写卡号”还不够，
        // 流程需要这个显式变量向后续环节证明卡数据从未被存储。
        assertEquals(false, out.get("cardDataStored"));
    }

    @Test
    @DisplayName("a second payment of the same amount is suppressed, not sent (REQ-22)")
    void duplicatePaymentIsSuppressed() {
        // 中文：给定同一组付款参数（同 episode、同金额、同币种），先执行一次
        // 完成首笔付款，然后再执行一次模拟重试（Given/When）。这是 Zeebe 重试
        // 语义下必然出现的场景：作业可能被投递两次。
        Map<String, Object> args = vars("patientId", "P-1", "episodeId", "EP-DUP",
                "chargeAmount", 480.0d, "currency", "GBP");
        run(new RequestSecurePaymentWorker(), args);
        Map<String, Object> second = run(new RequestSecurePaymentWorker(), args);
        // 中文：第二次执行必须被识别为重复并压制，这是 REQ-22“不得重复扣款”的
        // 执行层落点。若这里为 false，重试就会真的产生第二笔扣款。
        assertEquals(true, second.get("duplicatePaymentRequestSuppressed"));
        // 中文：同时要标记付款已存在，让流程知道可以继续推进（已有付款可用），
        // 而不是把它当成失败去重试——那会陷入无限循环。
        assertEquals(true, second.get("paymentAlreadyRecorded"));
        // 中文：绝不能为被压制的第二次请求编造新的交易流水号。若凭空造出一个，
        // 对账时会出现一笔并不存在的交易，退款也可能指向它。
        assertNull(second.get("paymentReference"), "no second transaction reference is invented");
    }

    // ---------------------------------------------------------- the other eight
    // 中文：其余八个 worker 不直接拥有网关变量，但同样承担变量读写契约与业务
    // 规则，因此逐个覆盖其成功路径与拒绝路径。

    @Test
    @DisplayName("send-referral-outcome notifies the decision it was given, and refuses to invent one")
    void referralOutcomeNeedsADecision() {
        // 中文：给定一个明确的转诊决定 rejected（Given），worker 必须原样通知
        // 该决定并回写同一个值（Then）。原样回写很重要：如果 worker 自作主张
        // 改写决定内容，家属收到的结论会与医生做出的判断不一致。
        Map<String, Object> out = run(new SendReferralOutcomeWorker(),
                vars("patientId", "P-1", "referralDecision", "rejected", "referringOrganisation", "GP surgery"));
        assertEquals(true, out.get("outcomeNotified"));
        assertEquals("rejected", out.get("outcomeNotifiedDecision"));

        // 中文：给定缺少转诊决定（Given/When），worker 必须抛业务错误而不是随便
        // 通知一个默认结论。这里检查的是 BPMN 错误码 REFERRAL_DECISION_MISSING，
        // 它是模型里错误边界事件依赖的标识，改名就会导致错误事件捕获不到。
        BpmnErrorException e = assertThrows(BpmnErrorException.class,
                () -> run(new SendReferralOutcomeWorker(), vars("patientId", "P-1")));
        assertEquals("REFERRAL_DECISION_MISSING", e.errorCode());
    }

    @Test
    @DisplayName("redirect-referral needs a destination and records the redirect")
    void redirectNeedsADestination() {
        // 中文：给定目标科室 Cardiology（Given），worker 应标记转诊已发出并把
        // 目标科室写回流程（Then），供后续随访与统计使用。
        Map<String, Object> out = run(new RedirectReferralWorker(),
                vars("patientId", "P-1", "redirectDestination", "Cardiology"));
        assertEquals(true, out.get("redirectSent"));
        assertEquals("Cardiology", out.get("redirectedToService"));
        // 中文：给定缺少目标科室（When），必须抛出校验异常而不是把转诊转到空目标。
        // 这条断言防止出现“转诊已发出但不知道发去哪”的悬空记录。
        assertThrows(ValidationException.class,
                () -> run(new RedirectReferralWorker(), vars("patientId", "P-1")));
    }

    @Test
    @DisplayName("request-missing-documentation names what is missing and sends the referral back")
    void missingDocumentationLoopsBack() {
        // 中文：给定用分号分隔的两项缺失资料（Given），worker 必须正确切分并
        // 计数为 2（Then）。计数用于判断资料是否补齐，若把整串当成一项，流程
        // 会误以为只缺一份材料。
        Map<String, Object> out = run(new RequestMissingDocumentationWorker(),
                vars("patientId", "P-1", "missingDocuments", "clinic letter; blood results"));
        assertEquals(true, out.get("missingDocumentsRequested"));
        assertEquals(2, out.get("missingDocumentCount"));
        // 中文：原始清单文本必须原样保留，回传给转诊机构时内容不能丢字或被改写，
        // 否则对方不知道具体要补哪几份材料。
        assertEquals("clinic letter; blood results", out.get("missingDocumentList"));
        // 中文：必须把 documentsComplete 复位为 false，这样流程才会回到完整性
        // 检查节点形成闭环（Given/Then）。若不复位，补件请求发出后流程仍认为
        // 资料完整，会直接跳过检查继续往下走。
        assertEquals(false, out.get("documentsComplete"), "the referral returns to the completeness check");
    }

    @Test
    @DisplayName("send-appointment-confirmation-letter needs the appointment it is confirming")
    void appointmentLetterNeedsAReference() {
        // 中文：给定一个有效的预约号 APT-1（Given），worker 应标记信件已发出，
        // 并生成带 LTR- 前缀的信件引用号（Then）。前缀是审计与对账时辨认信件
        // 类记录的标识，缺失或改前缀会让管理报表统计不到这类业务。
        Map<String, Object> out = run(new SendAppointmentConfirmationLetterWorker(),
                vars("patientId", "P-1", "appointmentReference", "APT-1"));
        assertEquals(true, out.get("appointmentLetterSent"));
        assertTrue(String.valueOf(out.get("appointmentLetterReference")).startsWith("LTR-"));
        // 中文：给定缺少预约号（When），必须抛出校验异常。确认信如果不指明确认的
        // 是哪次预约，对病人而言等于一封无效信件，属于必须拦截的输入缺失。
        assertThrows(ValidationException.class,
                () -> run(new SendAppointmentConfirmationLetterWorker(), vars("patientId", "P-1")));
    }

    @Test
    @DisplayName("correspondence is withheld until the Consultant has approved the letter")
    void correspondenceWaitsForApproval() {
        // 中文：场景一（Given/When/Then）——给定信件尚未获顾问批准（letterApproved
        // 为 false），worker 必须拒绝发出信件，并在拦截原因中说明“尚未批准”。
        // 这直接体现临床治理要求：未经医生审核的文书不得寄给病人。
        Map<String, Object> blocked = run(new DistributeClinicalCorrespondenceWorker(),
                vars("patientId", "P-1", "letterApproved", false));
        assertEquals(false, blocked.get("correspondenceSent"));
        assertTrue(String.valueOf(blocked.get("correspondenceBlockedReason")).contains("not yet approved"));

        // 中文：场景二（Given/When/Then）——信件已批准，但流程中标记了疑似临床
        // 错误。此时同样必须拦截并把原因指向临床错误，因为潜在的错误文书一旦
        // 寄出，造成的伤害远大于延迟发送。
        Map<String, Object> clinicalError = run(new DistributeClinicalCorrespondenceWorker(),
                vars("patientId", "P-1", "letterApproved", true, "suspectedClinicalError", true));
        assertEquals(false, clinicalError.get("correspondenceSent"));
        assertTrue(String.valueOf(clinicalError.get("correspondenceBlockedReason")).contains("clinical error"));

        // 中文：场景三（Given/When/Then）——既已批准又无临床错误，这是唯一的
        // 放行路径；信件应发出并生成 LTR- 前缀的引用号，作为确实寄出的凭据。
        Map<String, Object> sent = run(new DistributeClinicalCorrespondenceWorker(),
                vars("patientId", "P-1", "letterApproved", true, "suspectedClinicalError", false));
        assertEquals(true, sent.get("correspondenceSent"));
        assertTrue(String.valueOf(sent.get("correspondenceReference")).startsWith("LTR-"));
    }

    @Test
    @DisplayName("request-blood-test orders the test and leaves the clinical decision alone")
    void bloodTestDoesNotDecideFitness() {
        // 中文：给定周期引用（Given），worker 应登记化验申请、生成 LAB- 前缀的
        // 引用号并给出化验到期日（Then），供后续随访按时提醒。
        Map<String, Object> out = run(new RequestBloodTestWorker(),
                vars("patientId", "P-1", "cycleReference", "cycle 2"));
        assertEquals(true, out.get("bloodTestRequested"));
        assertTrue(String.valueOf(out.get("bloodTestReference")).startsWith("LAB-"));
        assertTrue(out.containsKey("bloodTestDueDate"));
        // 中文：最关键的是一条“不该写”的断言：worker 绝不能输出 fitToContinue。
        // 案例研究明确规定是否适合继续治疗属于临床判断，不能由自动化流程给出，
        // 因此这里用反向断言把这条边界钉死——一旦有人出于方便加上这个变量，
        // 测试会立刻失败并提示这属于越界实现。
        assertFalse(out.containsKey("fitToContinue"),
                "the case study says fitness is a clinical decision, not an automated one");
    }

    @Test
    @DisplayName("request-refund refuses without financial authority or without an original payment")
    void refundNeedsAuthorityAndAnOriginal() {
        // 中文：场景一（Given/When/Then）——有金额但没有财务授权。退款涉及资金
        // 流出，必须由有权限的人批准；未授权时状态应为 not authorised，绝不能
        // 因为“金额合法”就放行。
        Map<String, Object> unauthorised = run(new RequestRefundWorker(),
                vars("patientId", "P-1", "episodeId", "EP-R1", "refundAmount", 480.0d));
        assertEquals("not authorised", unauthorised.get("refundStatus"));

        // 中文：场景二（Given/When/Then）——已授权，但该 episode 下并不存在可退
        // 的原始付款。状态应为 no matching payment，防止凭空的资金流出。
        Map<String, Object> noOriginal = run(new RequestRefundWorker(),
                vars("patientId", "P-1", "episodeId", "EP-R2", "refundAmount", 480.0d, "refundAuthorised", true));
        assertEquals("no matching payment", noOriginal.get("refundStatus"));

        // 中文：场景三（Given/When/Then）——先直接向共享存储写入一笔原始付款，
        // 模拟此前已经真实收款；此时授权齐备且存在原交易，退款应成功（Then）。
        HospitalStore.get().put("EP-R3", "payments", "PAY-9", vars("amount", 480.0d, "currency", "GBP"));
        Map<String, Object> refunded = run(new RequestRefundWorker(),
                vars("patientId", "P-1", "episodeId", "EP-R3", "refundAmount", 480.0d, "refundAuthorised", true));
        assertEquals("refunded", refunded.get("refundStatus"));
        // 中文：成功退款必须带 REF- 前缀的引用号，它是财务对账与审计的凭据；
        // 没有它就无法证明这笔钱确实退了出去。
        assertTrue(String.valueOf(refunded.get("refundReference")).startsWith("REF-"));
    }

    @Test
    @DisplayName("generate-management-reports reports over the audit trail it can see")
    void reportingAggregatesTheAuditTrail() {
        // 中文：给定同一 episode、同一流程实例下的两条审计记录（Given）。这里
        // 直接写入日志而不是执行 worker，是为了把被测对象隔离成“统计逻辑”
        // 本身，避免上游 worker 的行为影响报表数字。
        OperationsLog.get().record("w", "request-secure-payment:completed", "EP-G", 5L, "T", vars());
        OperationsLog.get().record("w", "request-refund:completed", "EP-G", 5L, "T", vars());
        Map<String, Object> out = run(new GenerateManagementReportsWorker(),
                vars("patientId", "P-1", "episodeId", "EP-G", "reportPeriod", "2026-09"));
        // 中文：报表必须真的生成，并且回显被要求的统计区间，避免出现报表内容
        // 与申请区间不一致（例如默认按当月统计却声称是 2026-09）。
        assertEquals(true, out.get("reportGenerated"));
        assertEquals("2026-09", out.get("reportPeriod"));
        // 中文：报表引用号要带 RPT- 前缀，便于在审计中辨认并追溯某一期报表。
        assertTrue(String.valueOf(out.get("reportReference")).startsWith("RPT-"));
        // 中文：统计出的 auditedActivities 必须正好是 2，与写入的两条记录一致。
        // 这条断言防的是统计口径错误（漏计、重复计或把非本 episode 的记录算进来），
        // 报表数字失真会直接影响管理决策。
        assertEquals(2, ((Map<?, ?>) out.get("reportFigures")).get("auditedActivities"));
    }

    @Test
    @DisplayName("every worker reports the job type the models declare")
    void jobTypesMatchTheModels() {
        // 中文：场景（Given/When/Then）——逐个实例化全部十三个 worker，断言其
        // jobType() 的字符串与 BPMN 模型里 service task 声明的 type 完全一致
        // （Then）。这条断言针对的是一类非常隐蔽的故障：如果 worker 订阅的
        // job type 与模型声明的不一致，作业永远不会被这个 worker 领取，流程会
        // 静默地卡在服务任务上，既不报错也不推进——只有这种逐字比对才能挡住。
        assertEquals("request-missing-documentation", new RequestMissingDocumentationWorker().jobType());
        assertEquals("send-referral-outcome", new SendReferralOutcomeWorker().jobType());
        assertEquals("redirect-referral", new RedirectReferralWorker().jobType());
        assertEquals("query-available-appointment-slots", new QueryAvailableAppointmentSlotsWorker().jobType());
        assertEquals("send-appointment-confirmation-letter",
                new SendAppointmentConfirmationLetterWorker().jobType());
        assertEquals("request-treatment-capacity", new RequestTreatmentCapacityWorker().jobType());
        assertEquals("request-secure-payment", new RequestSecurePaymentWorker().jobType());
        assertEquals("distribute-clinical-correspondence",
                new DistributeClinicalCorrespondenceWorker().jobType());
        assertEquals("request-blood-test", new RequestBloodTestWorker().jobType());
        assertEquals("request-refund", new RequestRefundWorker().jobType());
        assertEquals("generate-management-reports", new GenerateManagementReportsWorker().jobType());
        // 中文：最后两个属于协作里第二个可执行池 PR_ReferringOrganisation。
        // 中文：消息抛出事件在引擎中同样是一个作业，所以跨池消息也有自己的 job type，
        // 中文：一旦这两个字符串与模型不一致，转诊就永远发不出去，且不会有任何报错。
        assertEquals("referring-org-submit-patient-referral",
                new SubmitPatientReferralWorker().jobType());
        assertEquals("referring-org-publish-patient-referral",
                new PublishPatientReferralWorker().jobType());
        // 中文：最后比较声明列表的元素个数与其去重后的个数，两者相等说明列表
        // 中没有重复声明。这个技巧用“计数比对”代替逐项查重：如果同一个 job type
        // 被登记两次，worker 会重复订阅同一类作业，导致每次任务被处理两遍。
        assertEquals(WorkersApplication.DECLARED_JOB_TYPES.size(),
                java.util.Set.copyOf(WorkersApplication.DECLARED_JOB_TYPES).size(),
                "the declared job types are a set, not a list with duplicates");
    }
}

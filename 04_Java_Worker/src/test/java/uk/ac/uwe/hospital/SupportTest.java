package uk.ac.uwe.hospital;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;
import uk.ac.uwe.hospital.support.OperationsLog;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The in-memory store and the audit log that the workers share.
 *
 * <p>中文：本测试类保护的是 worker 队伍共用的“支撑设施”：内存数据存储
 * （HospitalStore）、审计日志（OperationsLog）和引用号生成器（Ids）。它锁定的
 * 不变量是流程正确性与可审计性的基础：记录必须按 episode 关联键归档，重复
 * 付款必须能被识别出来（REQ-22 防重复扣款依赖它），预约索引必须让同一号源
 * 不会被预约两次，审计日志必须只追加、可按关联键查询，并且每条都带操作人、
 * 时间与动作（REQ-37 的审计要求）。引用号必须有可识别前缀且全局唯一，否则
 * 退款与对账就无法把一笔交易对应回它所属的 episode。
 */
class SupportTest {

    /**
     * 中文：每个用例结束后清空共享存储与审计日志，避免前一个用例写入的数据
     * 影响下一个用例的计数类断言（例如 count、size、attempts）。
     */
    @AfterEach
    void reset() {
        HospitalStore.get().clear();
        OperationsLog.get().clear();
    }

    @Test
    @DisplayName("records are filed under one episode correlation")
    void recordsAreCorrelated() {
        // 中文：给定两个属于不同 episode 的付款记录（Given）。episode 关联键
        // 是整个存储的隔离维度，所有后续查询都必须先落在这个维度里。
        HospitalStore store = HospitalStore.get();
        store.put("EP-P1", "payments", "PAY-1", Map.of("amount", 480.0d, "currency", "GBP"));
        store.put("EP-P2", "payments", "PAY-2", Map.of("amount", 20.0d, "currency", "GBP"));

        // 中文：EP-P1 下只应有 1 条付款记录，说明记录确实按 episode 分开归档，
        // 没有把两个人的数据混进同一个桶里。
        assertEquals(1, store.count("EP-P1", "payments"));
        // 中文：本 episode 自己的键能查到，别的 episode 的键查不到；前者防止
        // 数据写入后读不回，后者防止跨病人串号——在医疗系统里串号是严重事故。
        assertNotNull(store.get("EP-P1", "payments", "PAY-1"));
        assertNull(store.get("EP-P1", "payments", "PAY-2"));
        // 中文：取回的记录里必须回填 _key，因为后续 worker 用它引用这笔交易
        // （如退款指向原交易）。缺少 _key 会让引用链断裂。
        assertEquals("PAY-1", store.get("EP-P1", "payments", "PAY-1").get("_key"));
    }

    @Test
    @DisplayName("a duplicate payment of the same amount and currency is detected")
    void duplicatePaymentIsDetected() {
        // 中文：给定 EP-DUP 下已经存在一笔 480 GBP 的付款（Given）。这是重试
        // 或用户重复提交之后会出现的真实状态。
        HospitalStore store = HospitalStore.get();
        store.put("EP-DUP", "payments", "PAY-A", Map.of("amount", 480.0d, "currency", "GBP"));

        // 中文：同一 episode、同金额、同币种再次付款，必须被判为重复（Then），
        // 这是 REQ-22“不得重复扣款”在存储层的落点。若这里返回 false，重试一次
        // 就会真的扣两次钱。
        assertTrue(store.duplicatePayment("EP-DUP", 480.0d, "GBP"));
        // 中文：币种不同不算重复——480 GBP 与 480 EUR 是两笔不同性质的款项，
        // 误判会导致合法付款被错误拦截。
        assertFalse(store.duplicatePayment("EP-DUP", 480.0d, "EUR"), "a different currency is not a duplicate");
        // 中文：金额不同不算重复，防止“只要该 episode 付过款就一律拦截”的过度
        // 严格实现，那会让后续按周期收费的流程无法进行。
        assertFalse(store.duplicatePayment("EP-DUP", 481.0d, "GBP"), "a different amount is not a duplicate");
        // 中文：另一个 episode 的同额同币种付款不算重复，确认判重的作用域被正确
        // 限制在单个 episode 内，而不是全局比对。
        assertFalse(store.duplicatePayment("EP-OTHER", 480.0d, "GBP"), "another episode is not a duplicate");
    }

    @Test
    @DisplayName("attempts are counted per episode and activity")
    void attemptsAreCounted() {
        // 中文：给定全新存储（Given），attempts 计数必须从 0 开始，说明计数
        // 键在首次使用前不存在，而不是被初始化成 1 从而让后续计数整体偏移。
        HospitalStore store = HospitalStore.get();
        assertEquals(0, store.attempts("EP-A", "request-treatment-capacity"));
        // 中文：nextAttempt 返回“本次是第几次尝试”，即先自增再返回，因此连续
        // 两次调用得到 1 和 2。这个数字会被写进 capacityAttemptCount 变量，是
        // 判断是否触达尝试上限并升级的依据。
        assertEquals(1, store.nextAttempt("EP-A", "request-treatment-capacity"));
        assertEquals(2, store.nextAttempt("EP-A", "request-treatment-capacity"));
        // 中文：换成另一个 BPMN 活动 id 后计数重新从 1 开始，说明计数按
        // “episode + 活动”二维隔离。若两个活动共享一个计数器，付款重试次数
        // 会被容量重试次数污染，升级判断就会提前触发或永不触发。
        assertEquals(1, store.nextAttempt("EP-A", "request-secure-payment"));
        // 中文：换 episode 同样重新从 1 开始，避免不同病人的重试次数互相累加。
        assertEquals(1, store.nextAttempt("EP-B", "request-treatment-capacity"));
    }

    @Test
    @DisplayName("an appointment is indexed once and reported as existing afterwards")
    void appointmentIndexPreventsDoubleBooking() {
        // 中文：给定 EP-X 尚未索引过 APT-9（Given），首次查询应为空，代表该
        // 号源还没有被预约。
        HospitalStore store = HospitalStore.get();
        assertTrue(store.existingAppointment("EP-X", "APT-9").isEmpty());
        // 中文：索引一次后应报告已存在（Then），这正是 worker 判断“要不要真的
        // 去预约”的依据。若索引没生效，重复触发 worker 就会给同一个号源发两次
        // 预约请求，造成同一时段被占用两次。
        store.indexAppointment("EP-X", "APT-9", "BOOKING-1");
        assertTrue(store.existingAppointment("EP-X", "APT-9").isPresent());
        // 中文：再次索引同一号源时，必须保留最早那次预约（BOOKING-1）而不是被
        // 后来者（BOOKING-2）覆盖。这条“先到先得、后到忽略”的规则保证重复调用
        // 是幂等的，也保证审计上记录的预约凭据始终是最初真实发出的那一笔。
        store.indexAppointment("EP-X", "APT-9", "BOOKING-2");
        assertEquals("BOOKING-1", store.existingAppointment("EP-X", "APT-9").orElseThrow());
    }

    @Test
    @DisplayName("the audit log is append-only and queryable by correlation")
    void auditLogIsAppendOnly() {
        // 中文：给定三条审计记录，其中两条属于 EP-L、一条属于 EP-M（Given）。
        // 混合两个关联键是为了验证查询维度真的在过滤，而不是把全部记录都返回。
        OperationsLog log = OperationsLog.get();
        log.record("w1", "request-secure-payment:completed", "EP-L", 7L, "T_SendSecurePaymentRequest",
                Map.of("amount", 480.0d));
        log.record("w2", "request-refund:completed", "EP-L", 7L, "T_RequestRefund", Map.of("amount", 480.0d));
        log.record("w3", "query-available-appointment-slots:retry", "EP-M", 8L, "T_QueryAvailableSlots", Map.of());

        // 中文：日志只追加不清空，三条都应保留；这是可审计性的前提，任何一条
        // 被覆盖都会让事后追溯断链（REQ-37）。
        assertEquals(3, log.size());
        // 中文：按关联键查询必须精确返回属于该 episode 的记录数，EP-L 两条、
        // EP-M 一条。若查询忽略关联键，跨病人信息就会串到同一个视图里。
        assertEquals(2, log.forCorrelation("EP-L").size());
        assertEquals(1, log.forCorrelation("EP-M").size());
        // 中文：查询结果里每条记录都要带正确的关联键与流程实例 key，这样审计
        // 行才能反查回具体的 Zeebe 流程实例。这两条断言防的是“记录被归档到
        // 错误关联键下”这种会让审计报告张冠李戴的缺陷。
        assertEquals("EP-L", log.forCorrelation("EP-L").get(0).correlationId());
        assertEquals(7L, log.forCorrelation("EP-L").get(0).processInstanceKey());
        // the entry carries actor, time and action, which is what REQ-37 asks for
        // 中文：下面的三条断言共同保证每条审计记录都满足 REQ-37 的三要素。
        // 时间戳缺失则无法证明操作发生在何时，无法用于合规追溯。
        assertNotNull(log.all().get(0).at());
        // 中文：操作人不能是空白，否则无法回答“这件事是谁做的”，审计日志就
        // 失去了追责与复核价值。
        assertFalse(log.all().get(0).actor().isBlank());
        // 中文：action 必须包含冒号，因为约定格式是“jobType:结果”（如
        // request-refund:completed）。这条断言保证记录带上的是结构化结果而非
        // 自由文本，管理报表才能按结果分类统计。
        assertTrue(log.all().get(0).action().contains(":"));
    }

    @Test
    @DisplayName("references are unique and carry a recognisable prefix")
    void referencesAreUniqueAndPrefixed() {
        // 中文：两次生成的付款引用必须不同（Then）。唯一性是关键：若引用可重复，
        // 退款就会指向错误的原始交易，对账也会把两笔款项合并成一条。
        assertNotEquals(Ids.payment(), Ids.payment());
        // 中文：每种业务引用都必须带固定的前缀，前缀让人（和报表）一眼判断出
        // 这个引用属于哪类操作。这里逐一覆盖八种引用，防止新增类型时前缀被漏配
        // 或复制粘贴成同一个前缀。
        assertTrue(Ids.payment().startsWith("PAY-"));
        assertTrue(Ids.capacity().startsWith("CAP-"));
        assertTrue(Ids.letter().startsWith("LTR-"));
        assertTrue(Ids.laboratory().startsWith("LAB-"));
        assertTrue(Ids.refund().startsWith("REF-"));
        assertTrue(Ids.report().startsWith("RPT-"));
        assertTrue(Ids.scheduling().startsWith("SCH-"));
        assertTrue(Ids.request().startsWith("REQ-"));
    }

    @Test
    @DisplayName("the episode handle is derived from the patient and is stable")
    void episodeHandleIsStable() {
        // the handle is sanitised: only alphanumerics from the patient id survive,
        // so it is safe to use as a correlation key and as a store key
        // 中文：给定患者号 P-123（Given），episode 句柄必须是 EP-P123——连字符
        // 被去掉、加上 EP- 前缀。这个确定性映射让同一个病人在任何 worker 中都能
        // 算出同一个关联键，无需在流程里来回传递。
        assertEquals("EP-P123", Ids.episode("P-123"));
        // 中文：同一输入必须始终得到同一输出。稳定性是幂等性的前提：如果两次
        // 调用结果不同，重试时就会创建出第二个 episode，数据被劈成两半。
        assertEquals(Ids.episode("P-123"), Ids.episode("P-123"));
        // 中文：患者号缺失时回退到固定句柄 EP-UNKNOWN，保证流程变量不会是 null，
        // 避免下游按关联键查询时抛空指针。
        assertEquals("EP-UNKNOWN", Ids.episode(null));
        // 中文：空格和斜杠等特殊字符必须被过滤掉。这里断言净化结果中不含空格与
        // 斜杠，因为它们一旦进入关联键，就可能被当成日志分隔符或路径分隔符，
        // 造成日志解析错误甚至路径穿越式的键冲突。
        assertFalse(Ids.episode("P 1/2").contains(" "));
        assertFalse(Ids.episode("P 1/2").contains("/"));
    }
}

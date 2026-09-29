package uk.ac.uwe.hospital;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The read/write contract every worker is built on.
 *
 * <p>A missing variable in a Camunda 8 model does not raise an error - it
 * evaluates to a FEEL null and the gateway takes a branch nobody chose. Failing
 * loudly here is what stops that happening silently at run time.
 *
 * <p>中文：本测试类保护的是所有外部 worker 共用的“流程变量读写契约”，也就是
 * JobContext 这一层。它锁定的核心不变量是：必填变量缺失、为空或类型/取值
 * 非法时必须立刻抛出校验异常，而不是悄悄返回 null 或默认值。原因是 Camunda 8
 * 中缺失变量会被 FEEL 求值为 null，排他网关在条件都不成立时会走默认分支，
 * 于是一次数据缺失就变成了“没人选择过的路径”，并且没有任何报错。这个类还
 * 固定了可选读写的回退语义、输出变量的不可变性（防止 worker 绕过 outputs
 * 契约直接改流程数据）以及模拟开关的查找规则，因为这三者同样会被所有 worker
 * 依赖，一旦漂移会同时影响整支 worker 队伍。
 */
class JobContextTest {

    /**
     * 中文：测试辅助方法，构造一个固定元数据（job type、key、元素、重试次数）
     * 的 JobContext，只把变量表作为可变的输入参数。这样各用例只需关注变量
     * 本身，避免重复书写与断言无关的作业元数据。
     */
    private static JobContext ctx(Map<String, Object> vars) {
        return new JobContext("some-job-type", 1L, 2L, "T_Element", 3, vars);
    }

    @Test
    @DisplayName("a missing mandatory input is rejected by name")
    void missingMandatoryInputIsRejected() {
        // 中文：场景（Given/When/Then）——给定一个完全空的变量表（Given），
        // 当 worker 读取必填的 patientId 时（When），必须抛出校验异常（Then）。
        JobContext c = ctx(Map.of());
        ValidationException e = assertThrows(ValidationException.class, () -> c.requireString("patientId"));
        // 中文：异常必须带上出错的字段名，且既出现在结构化列表里也出现在可读
        // 消息里。这两条断言针对的是排障体验：如果只抛“参数错误”而不说是哪个
        // 变量，线上定位一个缺失字段要翻遍整张流程定义。
        assertTrue(e.missingFields().contains("patientId"));
        assertTrue(e.getMessage().contains("patientId"));
    }

    @Test
    @DisplayName("a blank mandatory input counts as missing")
    void blankMandatoryInputIsRejected() {
        // 中文：给定变量存在但只有空白字符（Given/When）。这是表单或接口传参
        // 最常见的脏数据形态，必须与“完全缺失”同等对待；否则空白机构名会被
        // 写进流程变量，后续按机构分支或对外信件都会出现空白内容。
        JobContext c = ctx(Map.of("referringOrganisation", "  "));
        assertThrows(ValidationException.class, () -> c.requireString("referringOrganisation"));
    }

    @Test
    @DisplayName("a mandatory flag that is neither true nor false is rejected")
    void malformedFlagIsRejected() {
        // 中文：给定布尔变量被写成字符串 "yes"（Given/When）。这里要防的是把
        // 非法字符串宽松地当作 true，因为一个被误判为“已批准”的信件标记会
        // 直接导致未经医生审核的临床文书被寄出。
        JobContext c = ctx(Map.of("letterApproved", "yes"));
        assertThrows(ValidationException.class, () -> c.requireBool("letterApproved"));
    }

    @Test
    @DisplayName("a missing flag is rejected rather than defaulted to false")
    void missingFlagIsRejected() {
        // 中文：给定布尔变量完全缺失（Given/When）。它强调不能静默地按 false
        // 兜底：默认 false 会让流程安静地走向“资料不完整”的重回分支，而真实
        // 原因可能是上游根本没写这个变量，属于需要立即暴露的建模缺陷。
        JobContext c = ctx(Map.of());
        assertThrows(ValidationException.class, () -> c.requireBool("documentsComplete"));
    }

    @Test
    @DisplayName("optional reads fall back instead of throwing")
    void optionalReadsFallBack() {
        // 中文：给定一个字符串形式的数值变量（Given）。注意流程变量经序列化
        // 后经常以字符串到达 worker，因此数值读取必须能容忍字符串形态。
        JobContext c = ctx(Map.of("treatmentCycles", "6"));
        // 中文：字符串 "6" 能被正确解析为整数 6，说明做了类型转换而不是强制
        // 转型（强转会直接抛 ClassCastException，让整个 worker 失败）。
        assertEquals(6, c.intOr("treatmentCycles", 1));
        // 中文：变量缺失时返回调用方给的默认值，这是可选读取与必填读取的关键
        // 区别：可选字段缺了不该打断流程，必填字段缺了必须打断。
        assertEquals(1, c.intOr("missing", 1));
        // 中文：已有值时优先使用实际值，而不是回退值。这里用条件表达式把
        // “读到的确实是 6 而非 99”写进断言，防止默认值悄悄覆盖了真实数据。
        assertEquals(1, c.intOr("treatmentCycles", 99) == 6 ? 1 : 99);
        // 中文：金额允许以字符串 "480.0" 传入并解析为 double，对应表单提交的
        // 真实形态；若失败，收费金额会变成 0，付款流程直接错算。
        assertEquals(480.0d, ctx(Map.of("chargeAmount", "480.0")).doubleOr("chargeAmount", 0.0d));
        // 中文：原生 double 类型也应直接读取成功，覆盖另一种入参形态。
        assertEquals(7.5d, ctx(Map.of("x", 7.5d)).doubleOr("x", 0.0d));
        // 中文：布尔可选读取在变量缺失时，必须原样返回调用方给出的默认值——
        // 传 true 得 true，传 false 得 false。这两条一起证明它不是硬编码默认值。
        assertTrue(c.bool("absent", true));
        assertFalse(c.bool("absent", false));
    }

    @Test
    @DisplayName("written variables come back as an immutable copy")
    void outputsAreImmutable() {
        // 中文：给定一个空上下文，写入一个布尔变量和一批变量（When）。
        JobContext c = ctx(Map.of());
        c.set("suitableSlotFound", true).setAll(Map.of("availableSlotCount", 2));
        Map<String, Object> out = c.outputs();
        // 中文：写进去的值必须能被读回来，这是 worker 向流程回传结果的基本
        // 契约，网关变量全靠这条链路才能生效。
        assertEquals(true, out.get("suitableSlotFound"));
        assertEquals(2, out.get("availableSlotCount"));
        // 中文：输出必须是不可变副本，任何外部修改都要抛异常。这防止调用方
        // 在完成 job 之后还能偷偷改动待提交的变量集，从而出现“日志里记录的
        // 结果与实际提交给 Zeebe 的结果不一致”这种极难排查的问题。
        assertThrows(UnsupportedOperationException.class, () -> out.put("sneaky", 1));
    }

    @Test
    @DisplayName("a simulation override is read from the simulate* variable")
    void simulationOverrideIsFound() {
        // 中文：给定流程变量中带有 simulatePaymentOutcome（Given），当按名字
        // paymentOutcome 查找模拟开关时（When），应命中并返回其值（Then）。
        // 命名约定是 simulate + 首字母大写，这条断言把这个约定钉死。
        Map<String, Object> vars = new HashMap<>();
        vars.put("simulatePaymentOutcome", "DECLINED");
        assertEquals("DECLINED", ctx(vars).findSimulation("paymentOutcome").orElseThrow());
        // 中文：没有设置开关时必须返回 empty 而不是抛异常或返回默认字符串，
        // 这样 worker 才能安全地用“开关是否存在”来决定走真实逻辑还是演示逻辑。
        assertTrue(ctx(Map.of()).findSimulation("paymentOutcome").isEmpty());
    }

    @Test
    @DisplayName("the context describes itself for the log")
    void describesItself() {
        // 中文：给定上下文（Given），当输出其字符串描述时（When），必须包含
        // job type、BPMN 元素 id 与重试次数（Then）。这三点是线上排障的定位
        // 三要素：哪个任务、流程停在哪一步、还剩几次重试；缺任何一个，日志都
        // 无法把一次失败关联回具体的流程实例。
        String s = ctx(Map.of()).toString();
        assertTrue(s.contains("some-job-type"));
        assertTrue(s.contains("T_Element"));
        assertTrue(s.contains("retries=3"));
    }
}

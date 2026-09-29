package uk.ac.uwe.hospital.support;

import java.security.SecureRandom;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

/**
 * 中文：为流程中需要记录的业务标识提供统一的生成入口。所有编号共享同一种结构，即业务前缀
 * 加日期加随机位，使编号自身携带类型与时间信息，便于在日志与审计记录中直接辨认和按日筛查；
 * 随机化则避免编号可被外部顺序推测。日期采用固定的两位年月日格式，长度稳定，不随区域设置变化。
 *
 * <p>Reference generators for the business identifiers the process records.
 */
public final class Ids {

    /** 中文：使用加密强度随机源，使编号不可预测；SecureRandom 本身线程安全，可被多个工作者共享。 */
    private static final SecureRandom RANDOM = new SecureRandom();
    /** 中文：固定的两位年月日格式，与区域设置无关，保证编号长度与排序方式稳定。 */
    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("yyMMdd");

    /** 中文：工具类不需要实例，私有构造器用于阻止实例化。 */
    private Ids() {
    }

    /**
     * 中文：统一编号格式为“前缀-两位年月日-随机数字”。日期段提供日期语义，便于按天归档与人工核对；
     * 随机段使用加密强度随机源，避免顺序编号被外部猜测。该编号仅在演示规模下要求唯一，
     * 并不承担全局去重职责，因此不查重也不重试。
     */
    private static String code(String prefix, int digits) {
        // 中文：先写入业务前缀与日期，两段均定长，因此编号的固定部分长度不随随机位变化。
        StringBuilder sb = new StringBuilder(prefix).append('-').append(LocalDate.now().format(DAY)).append('-');
        // 中文：逐位取 0 到 9 的随机数。取值范围与模数相同，不存在取模偏差，各位可视为均匀独立。
        for (int i = 0; i < digits; i++) {
            sb.append(RANDOM.nextInt(10));
        }
        // 中文：返回“前缀-日期-随机位”的完整编号；随机位不参与排序，仅用于降低碰撞概率。
        return sb.toString();
    }

    public static String scheduling() {
        return code("SCH", 6);
    }

    public static String capacity() {
        return code("CAP", 6);
    }

    public static String payment() {
        return code("PAY", 8);
    }

    public static String refund() {
        return code("REF", 6);
    }

    public static String letter() {
        return code("LTR", 6);
    }

    public static String laboratory() {
        return code("LAB", 6);
    }

    public static String report() {
        return code("RPT", 5);
    }

    public static String request() {
        return code("REQ", 6);
    }

    public static String redirect() {
        return code("RDR", 5);
    }

    /**
     * 中文：转诊编号。它同时充当跨池消息的关联键，因此前缀与退款用的 REF 区分开，
     * 避免在日志与审计记录里把两种业务编号看混。
     *
     * <p>Reference for a referral, used as the correlation key of the cross-pool
     * {@code Patient referral} message. It is kept distinct from {@link #refund()}
     * so the two are not confused in the audit log.
     */
    public static String referral() {
        return code("REFRL", 6);
    }

    /**
     * 中文：生成关联句柄。患者号先移除非字母数字字符再转为大写，使同一患者无论提交格式如何
     * 都落到同一条关联链路上，既保证端到端可追溯，也避免特殊字符进入存储键与日志。
     * 患者号缺失时退化为固定占位符而不是抛错，以免流程因数据不完整而中断。
     *
     * <p>Correlation handle for the patient, referral, treatment and payment chain.
     */
    public static String episode(String patientId) {
        // 中文：清洗患者号并统一大写，使同一患者的不同书写形式归一为同一关联键。
        String safe = patientId == null ? "UNKNOWN" : patientId.replaceAll("[^A-Za-z0-9]", "");
        // 中文：加固定前缀形成句柄，避免纯数字键与流程变量中的其他标识产生语义混淆。
        return "EP-" + safe.toUpperCase();
    }
}

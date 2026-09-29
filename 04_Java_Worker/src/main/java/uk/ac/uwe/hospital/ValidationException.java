package uk.ac.uwe.hospital;

import java.util.Set;

/**
 * A mandatory input is missing or malformed. This is a defect in the model or in
 * the form that feeds it, not a provider outage, so it is reported as a named
 * BPMN error rather than retried.
 *
 * <p>中文：表示必需的输入缺失或格式非法，属于模型或表单的数据缺陷，而不是外部服务故障。</p>
 * <p>中文：基类会把它转换成错误码为 INVALID_JOB_INPUT 的 BPMN 错误而不是重试，
 * 因为用同样的错误数据重试只会重复失败，直到耗光重试次数并产生 incident。</p>
 * <p>中文：异常携带具体的字段名集合，使日志与审计能直接指出到底是哪个变量出了问题。</p>
 */
public class ValidationException extends RuntimeException {

    /** 中文：记录触发本异常的变量名，供上层拼装精确的错误消息。 */
    private final Set<String> missing;

    /** 中文：除了字段名，再附一句人类可读的说明，便于直接在日志中定位问题。 */
    public ValidationException(Set<String> missing, String message) {
        super(message);
        // 中文：用 Set.copyOf 做防御性拷贝，避免外部集合事后被改动而影响异常内容。
        this.missing = Set.copyOf(missing);
    }

    /** 中文：返回缺失字段名，基类在拼装 INVALID_JOB_INPUT 的错误消息时会用到。 */
    public Set<String> missingFields() {
        return missing;
    }
}

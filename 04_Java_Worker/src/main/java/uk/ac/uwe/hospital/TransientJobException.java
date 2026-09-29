package uk.ac.uwe.hospital;

/**
 * An external service failed in a way that is worth another attempt. The worker
 * base class fails the job and decrements the remaining retries rather than
 * raising an incident, so a flaky provider does not stop the instance.
 *
 * <p>中文：用于标记“值得再试一次”的失败，例如下游服务超时、临时不可用或返回 5xx。</p>
 * <p>中文：基类会以剩余重试次数减一的方式 fail 作业，由引擎按重试语义稍后重新激活，
 * 因此短暂的第三方抖动不会让流程实例停下来等人处理。</p>
 * <p>中文：与 BpmnErrorException 的分工是：业务上无法继续的分支抛 BPMN 错误，
 * 只是暂时失败、稍后可能成功的抛本异常。</p>
 */
public class TransientJobException extends RuntimeException {

    /** 中文：只带说明信息，适用于无需保留原始堆栈的简单重试场景。 */
    public TransientJobException(String message) {
        super(message);
    }

    /** 中文：保留底层异常作为 cause，便于在日志与审计中定位真正的故障来源。 */
    public TransientJobException(String message, Throwable cause) {
        super(message, cause);
    }
}

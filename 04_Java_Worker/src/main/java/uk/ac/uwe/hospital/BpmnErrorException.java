package uk.ac.uwe.hospital;

/**
 * A business error the process is expected to catch with a boundary event.
 *
 * <p>中文：表示“业务错误”，即流程模型自身预期会处理的异常情况，而不是技术故障。</p>
 * <p>中文：基类捕获它后调用 throwError 命令把错误码交还引擎，由边界事件或事件子流程
 * 按模型定义的业务分支接管，因此它既不消耗重试次数，也不会升级为 incident。</p>
 * <p>中文：errorCode 必须与 BPMN 中 error 元素的 code 属性逐字一致，否则引擎匹配不到
 * 捕获点，作业会停在原活动上，表现为流程“卡住”而不是报错。</p>
 */
public class BpmnErrorException extends RuntimeException {

    private final String errorCode;

    /** 中文：错误码在构造时一次性确定并保持不可变，供基类回传引擎时读取。 */
    public BpmnErrorException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    /** 中文：暴露错误码，保证抛出端与模型中声明的捕获事件使用同一个字面量。 */
    public String errorCode() {
        return errorCode;
    }
}

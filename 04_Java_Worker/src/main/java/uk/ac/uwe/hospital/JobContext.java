package uk.ac.uwe.hospital;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * A typed, read-only view of one activated job plus the variables the worker
 * wants to write back.
 *
 * <p>Every accessor is validated: a worker asks for what it needs and the base
 * class turns a missing key into a {@link ValidationException} carrying the
 * names, so a broken form or a mistyped variable is reported once, clearly,
 * instead of surfacing later as a FEEL null on a gateway.
 *
 * <p>中文：这是一次已激活作业的类型化视图，既提供只读的输入读取，也收集本工作器要写回的变量。</p>
 * <p>中文：读取侧把“变量缺失”在数据入口处就变成带字段名的 ValidationException，
 * 而不是等流程走到网关时因 FEEL 取到 null 才以难以定位的方式失败。</p>
 * <p>中文：写入侧只是登记待输出变量，真正的提交由基类在完成作业时统一执行，
 * 因此工作器中途抛错也不会留下写了一半的流程变量。</p>
 */
public final class JobContext {

    // 中文：全部字段都是 final，且在作业回调内一次性构造，因此天然只被单线程使用。
    private final String jobType;
    private final long jobKey;
    private final long processInstanceKey;
    private final String elementId;
    private final int retries;
    // 中文：构造时已经做过空值兜底，后续读取不必再判断 variables 本身是否为 null。
    private final Map<String, Object> variables;
    // 中文：out 只收集本工作器显式写出的变量，是“输出变量白名单”的实际载体。
    private final Map<String, Object> out = new java.util.LinkedHashMap<>();
    // 中文：备注只进入日志，不会写入流程变量，因此可以承载内部诊断信息。
    private final List<String> notes = new ArrayList<>();

    /** 中文：由基类在作业被激活时构造，直接采信引擎给出的键、元素标识与剩余重试次数。 */
    public JobContext(String jobType, long jobKey, long processInstanceKey, String elementId,
                      int retries, Map<String, Object> variables) {
        this.jobType = jobType;
        this.jobKey = jobKey;
        this.processInstanceKey = processInstanceKey;
        this.elementId = elementId;
        this.retries = retries;
        this.variables = variables == null ? Map.of() : variables;
    }

    // ------------------------------------------------------------------ reads

    // 中文：以下为只读访问器，只读取作业快照，不触发引擎调用，也没有副作用。
    public String jobType() {
        return jobType;
    }

    public long jobKey() {
        return jobKey;
    }

    public long processInstanceKey() {
        return processInstanceKey;
    }

    public String elementId() {
        return elementId;
    }

    public int retries() {
        return retries;
    }

    /** 中文：以“非 null”作为存在性判断，因此显式写入的 null 会被视为不存在。 */
    public boolean has(String name) {
        return variables.get(name) != null;
    }

    /** 中文：统一按字符串取值，兼容引擎返回数字或布尔值的情况，缺失时返回空。 */
    public Optional<String> findString(String name) {
        Object v = variables.get(name);
        return v == null ? Optional.empty() : Optional.of(String.valueOf(v));
    }

    /** 中文：强制读取字符串输入，空白字符串同样视为缺失，从源头挡住“空值绕过”。 */
    public String requireString(String name) {
        Object v = variables.get(name);
        // 中文：null 与纯空白一并拒绝，因为空白值流到网关同样会变成难以解释的空分支。
        if (v == null || String.valueOf(v).isBlank()) {
            throw new ValidationException(Set.of(name), "missing mandatory input '" + name + "'");
        }
        return String.valueOf(v);
    }

    /** 中文：宽松读取布尔标志，变量缺失时返回调用方给出的默认值而不是抛错。 */
    public boolean bool(String name, boolean fallback) {
        Object v = variables.get(name);
        if (v == null) {
            return fallback;
        }
        if (v instanceof Boolean b) {
            return b;
        }
        // 中文：兼容字符串形式的布尔值，例如表单或 REST 接口传入的 "true"。
        return Boolean.parseBoolean(String.valueOf(v));
    }

    /** 中文：强制读取布尔标志，缺失或取值非法都直接判定为数据缺陷。 */
    public boolean requireBool(String name) {
        Object v = variables.get(name);
        if (v == null) {
            throw new ValidationException(Set.of(name), "missing mandatory flag '" + name + "'");
        }
        if (v instanceof Boolean b) {
            return b;
        }
        String s = String.valueOf(v);
        // 中文：这里比 Boolean.parseBoolean 更严格，只接受 true/false；因为把 "yes"
        // 静默当成 false 会让流程走到错误的分支，而这属于模型缺陷而非数据噪声。
        if (!s.equalsIgnoreCase("true") && !s.equalsIgnoreCase("false")) {
            throw new ValidationException(Set.of(name), "'" + name + "' is not a boolean: " + s);
        }
        return Boolean.parseBoolean(s);
    }

    /** 中文：读取整型参数，缺失或无法解析时一律退回默认值，避免可选参数打断流程。 */
    public int intOr(String name, int fallback) {
        Object v = variables.get(name);
        if (v == null) {
            return fallback;
        }
        if (v instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(v));
        } catch (NumberFormatException e) {
            // 中文：解析失败按“未提供”处理，属于宽松语义，仅适用于可选参数。
            return fallback;
        }
    }

    /** 中文：读取浮点参数，语义与 intOr 一致，供概率、阈值等可选数值使用。 */
    public double doubleOr(String name, double fallback) {
        Object v = variables.get(name);
        if (v == null) {
            return fallback;
        }
        if (v instanceof Number n) {
            return n.doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(v));
        } catch (NumberFormatException e) {
            // 中文：同样静默退回默认值，调用方无需处理解析异常。
            return fallback;
        }
    }

    /**
     * Every variable name that looks like a deliberate test override.
     *
     * <p>中文：按约定读取 {@code simulateXxx} 形式的变量，用于在演示中覆盖某个外部系统的
     * 真实结果；命名规则集中在这里，避免各处手写前缀字符串。</p>
     */
    public Optional<String> findSimulation(String name) {
        // 中文：把首字母大写后拼接 simulate 前缀，得到形如 simulatePatientId 的变量名。
        return findString("simulate" + Character.toUpperCase(name.charAt(0)) + name.substring(1));
    }

    // ----------------------------------------------------------------- writes

    // 中文：以下写入方法只登记待写出的变量，真正的提交发生在作业完成命令中。
    /**
     * Write a process variable. Never pass personal or card data through here.
     *
     * <p>中文：流程变量会随完成命令进入引擎，并可能出现在历史记录与运维界面中，
     * 因此个人身份信息与银行卡数据不得经由这里传递。</p>
     */
    public JobContext set(String name, Object value) {
        out.put(name, value);
        return this;
    }

    /** 中文：批量登记输出变量，常用于把外部响应或子流程结果整体回写。 */
    public JobContext setAll(Map<String, Object> values) {
        out.putAll(values);
        return this;
    }

    /** 中文：追加一条只写入日志的备注；它不进入流程变量，因此可以承载诊断细节。 */
    public JobContext note(String text) {
        notes.add(text);
        return this;
    }

    /** 中文：返回不可变的输出快照，调用方无法在作业提交前再改写待写变量。 */
    public Map<String, Object> outputs() {
        return Map.copyOf(out);
    }

    /** 中文：返回不可变的备注快照，供日志与审计按写入顺序读取。 */
    public List<String> notes() {
        return List.copyOf(notes);
    }

    /** 中文：诊断用文本，只包含类型、键与元素等标识信息，不会泄漏变量内容。 */
    @Override
    public String toString() {
        return jobType + "#" + jobKey + " element=" + elementId
                + " instance=" + processInstanceKey + " retries=" + retries;
    }
}

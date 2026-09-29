package uk.ac.uwe.hospital.support;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory record of the business objects the workers create.
 *
 * <p>This exists for two reasons. It gives the workers something to be
 * consistent <em>about</em> - a second payment attempt can see the first
 * transaction, a capacity retry can see its earlier attempts, a duplicate
 * booking can be detected rather than created - and it gives the episode
 * correlation that REQ-44 asks for: every record is filed under one handle
 * covering patient, referral, treatment request, appointment and payment.
 *
 * <p>It is deliberately not a database. Nothing here survives a restart, and the
 * acceptance evaluation says so.
 *
 * <p>中文：这是一个进程内的业务记录仓库，作用有两层。其一是给工作者提供一致性判定的依据：
 * 再次付款时能看到首笔交易，容量重试时能看到先前的尝试，重复预约能被识别而不是被重复创建。
 * 其二是提供需求要求的端到端关联：患者、转诊、治疗申请、预约与付款全部归档在同一个关联句柄下。
 * 它刻意不是数据库，进程重启后数据全部丢失，这一局限已在验收说明中明确，而不是被掩盖。
 * 因此这里的语义只保证单进程内可见，不承诺持久化与跨实例共享。
 */
public final class HospitalStore {

    /** 中文：进程级单例。工作者之间必须共享同一份视图，否则重复检测与尝试计数都会失效。 */
    private static final HospitalStore INSTANCE = new HospitalStore();

    /** 中文：三层映射依次是关联句柄、集合名与记录键；用并发容器保证多工作者同时写入时不丢记录。 */
    private final Map<String, Map<String, Map<String, Object>>> byCorrelation = new ConcurrentHashMap<>();
    /** 中文：预约去重索引，键由关联句柄与预约号拼成，使同一句柄下重复确认同一预约可被识别。 */
    private final Map<String, String> appointmentIndex = new ConcurrentHashMap<>();

    /** 中文：单例模式，构造器私有以避免出现第二份互不可见的状态。 */
    private HospitalStore() {
    }

    /** 中文：返回全局唯一实例；所有工作者读写同一份记录，这是业务一致性的前提。 */
    public static HospitalStore get() {
        return INSTANCE;
    }

    /**
     * File a record against the episode. Returns the stored record.
     * <p>中文：按关联句柄归档一条记录并返回存储后的副本。写入前复制并补齐 _key，调用方后续修改不会影响库内数据。</p>
     */
    public Map<String, Object> put(String correlationId, String collection, String key, Map<String, Object> value) {
        // 中文：写入的是副本，并把业务键补进 _key，确保存储内容自描述且不被外部改动。
        Map<String, Object> record = new LinkedHashMap<>(value);
        record.putIfAbsent("_key", key);
        // 中文：合并而非覆盖，使同一集合下的不同记录键可以累积，形成该集合的完整快照。
        byCorrelation
                .computeIfAbsent(correlationId == null ? "-" : correlationId, k -> new ConcurrentHashMap<>())
                .merge(collection, new LinkedHashMap<>(Map.of(key, record)),
                        (existing, incoming) -> {
                            Map<String, Object> merged = new LinkedHashMap<>(existing);
                            merged.putAll(incoming);
                            return merged;
                        });
        return Collections.unmodifiableMap(record);
    }

    /** 中文：按键读取单条记录；关联句柄或集合不存在时返回 null，表示“未记录”而非错误。 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> get(String correlationId, String collection, String key) {
        Map<String, Map<String, Object>> collections = byCorrelation.get(correlationId == null ? "-" : correlationId);
        if (collections == null) {
            return null;
        }
        Map<String, Object> coll = collections.get(collection);
        if (coll == null) {
            return null;
        }
        return (Map<String, Object>) coll.get(key);
    }

    /**
     * 中文：列出某个集合的全部记录，返回不可变副本，避免调用方在遍历时被并发写入干扰。
     * 集合不存在时返回空列表，使调用方无需先判空，也符合“从未写入”的语义。
     */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> list(String correlationId, String collection) {
        Map<String, Map<String, Object>> collections = byCorrelation.get(correlationId == null ? "-" : correlationId);
        if (collections == null || collections.get(collection) == null) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object v : collections.get(collection).values()) {
            out.add((Map<String, Object>) v);
        }
        return List.copyOf(out);
    }

    /** 中文：统计记录条数，等价于列出后再取大小，因此与 list 的可见性语义完全一致。 */
    public long count(String correlationId, String collection) {
        return list(correlationId, collection).size();
    }

    /**
     * 中文：查询某次预约是否已登记过并返回已有预约记录。
     * 同一预约不能被确认两次，这正是案例研究要求的防重复规则。
     *
     * <p>Records the appointment reference and reports whether this appointment
     * already exists. The process must not confirm the same appointment twice,
     * which is the anti-duplication rule the case study asks for.
     */
    public Optional<String> existingAppointment(String correlationId, String appointmentReference) {
        String key = (correlationId == null ? "-" : correlationId) + '|' + appointmentReference;
        return Optional.ofNullable(appointmentIndex.get(key));
    }

    /** 中文：登记预约索引。用 putIfAbsent 保留首次写入的预约号，重复登记不会覆盖既有结果。 */
    public void indexAppointment(String correlationId, String appointmentReference, String bookingId) {
        String key = (correlationId == null ? "-" : correlationId) + '|' + appointmentReference;
        appointmentIndex.putIfAbsent(key, bookingId);
    }

    /**
     * 中文：判断该关联下是否已存在金额与币种相同的交易。
     * 金额用容差比较而非等值比较，因为浮点累加会产生微小误差，等值判断会导致漏判重复。
     *
     * <p>True when a transaction for this amount and provider already exists.
     */
    public boolean duplicatePayment(String correlationId, double amount, String currency) {
        for (Map<String, Object> p : list(correlationId, "payments")) {
            Object amt = p.get("amount");
            Object cur = p.get("currency");
            if (amt != null && cur != null
                    && Math.abs(Double.parseDouble(String.valueOf(amt)) - amount) < 0.005
                    && currency.equalsIgnoreCase(String.valueOf(cur))) {
                return true;
            }
        }
        return false;
    }

    /** 中文：读取某活动的尝试次数，缺失记录时返回 0，表示尚未尝试过，从而让首次调用自然为 1。 */
    public int attempts(String correlationId, String activity) {
        Object v = get(correlationId, "attempts", activity) == null
                ? null : get(correlationId, "attempts", activity).get("count");
        return v == null ? 0 : Integer.parseInt(String.valueOf(v));
    }

    /** 中文：把尝试次数加一并写回，返回新值；外部服务据此判断“只失败一次”的注入规则是否仍然有效。 */
    public int nextAttempt(String correlationId, String activity) {
        int next = attempts(correlationId, activity) + 1;
        put(correlationId, "attempts", activity, Map.of("count", next, "at", LocalDate.now().toString()));
        return next;
    }

    /** 中文：清空全部记录与索引，用于测试隔离或重放演示，不建议在正常业务路径中调用。 */
    public void clear() {
        byCorrelation.clear();
        appointmentIndex.clear();
    }
}

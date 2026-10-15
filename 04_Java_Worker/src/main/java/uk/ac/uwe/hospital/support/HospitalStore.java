package uk.ac.uwe.hospital.support;

import com.fasterxml.jackson.core.type.TypeReference;

import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Durable record of the business objects the workers create.
 *
 * <p>This exists for two reasons. It gives the workers something to be consistent
 * <em>about</em> - a second payment attempt can see the first transaction, a capacity retry
 * can see its earlier attempts, a duplicate booking can be detected rather than created -
 * and it gives the episode correlation that REQ-44 asks for: every record is filed under
 * one handle covering patient, referral, treatment request, appointment and payment.
 *
 * <p>Until review item 1 it was a map in the process, and the acceptance evaluation said
 * so: nothing survived a restart. It is now backed by the embedded database in
 * {@link Database}, so the records and the episode correlation outlive the worker. The
 * public surface is unchanged, so no worker had to be rewritten.
 *
 * <p>中文：这是业务记录的持久化仓库，作用有两层。其一是给工作者提供一致性判定的依据：再次付款时
 * 能看到首笔交易，容量重试时能看到先前的尝试，重复预约能被识别而不是被重复创建。其二是提供需求
 * 要求的端到端关联：患者、转诊、治疗申请、预约与付款全部归档在同一个关联句柄下。在整改清单第 1 项
 * 之前，这些状态只存在于进程内存中，验收说明也如实写明重启即失；现在改为落在嵌入式数据库中，
 * 记录与关联关系都能跨重启保留。对外方法签名保持不变，因此没有任何工作者需要改写。
 */
public final class HospitalStore {

    /** 中文：进程级单例。工作者之间必须共享同一份视图，否则重复检测与尝试计数都会失效。 */
    private static final HospitalStore INSTANCE = new HospitalStore();

    /** 中文：单例模式，构造器私有以避免出现第二份互不可见的状态。 */
    private HospitalStore() {
    }

    /** 中文：返回全局唯一实例；所有工作者读写同一份记录，这是业务一致性的前提。 */
    public static HospitalStore get() {
        return INSTANCE;
    }

    /** 中文：把关联句柄规范化为非空字符串，缺失时归入占位键，避免空值进入主键。 */
    private static String scope(String correlationId) {
        return correlationId == null ? "-" : correlationId;
    }

    /**
     * File a record against the episode. Returns the stored record.
     *
     * <p>中文：按关联句柄归档一条记录并返回存储后的副本。写入前复制并补齐 _key，
     * 同一主键再次写入即为覆盖，调用方后续修改不会影响库内数据。
     */
    public Map<String, Object> put(String correlationId, String collection, String key,
                                   Map<String, Object> value) {
        Map<String, Object> record = new LinkedHashMap<>(value);
        record.putIfAbsent("_key", key);
        Database.inConnection("cannot store " + collection + '/' + key, c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    MERGE INTO record (correlation_id, collection, record_key, payload, updated_at)
                    KEY (correlation_id, collection, record_key) VALUES (?, ?, ?, ?, ?)""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, collection);
                ps.setString(3, key);
                ps.setString(4, Database.json().writeValueAsString(record));
                ps.setTimestamp(5, Timestamp.from(Instant.now()));
                ps.executeUpdate();
            }
            return null;
        });
        return Collections.unmodifiableMap(record);
    }

    /** 中文：按键读取单条记录；不存在时返回 null，表示“未记录”而非错误。 */
    public Map<String, Object> get(String correlationId, String collection, String key) {
        return Database.inConnection("cannot read " + collection + '/' + key, c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    SELECT payload FROM record
                    WHERE correlation_id = ? AND collection = ? AND record_key = ?""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, collection);
                ps.setString(3, key);
                try (ResultSet rs = ps.executeQuery()) {
                    return rs.next() ? parse(rs.getString(1)) : null;
                }
            }
        });
    }

    /**
     * 中文：列出某个集合的全部记录，按写入时间与记录键排序，保证同一份数据每次读出的顺序一致。
     * 集合不存在时返回空列表，使调用方无需先判空，也符合“从未写入”的语义。
     */
    public List<Map<String, Object>> list(String correlationId, String collection) {
        return Database.inConnection("cannot list " + collection, c -> {
            List<Map<String, Object>> out = new ArrayList<>();
            try (PreparedStatement ps = c.prepareStatement("""
                    SELECT payload FROM record
                    WHERE correlation_id = ? AND collection = ?
                    ORDER BY updated_at, record_key""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, collection);
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        out.add(parse(rs.getString(1)));
                    }
                }
            }
            return List.copyOf(out);
        });
    }

    /** 中文：统计记录条数，直接由数据库计数，避免把全部记录读进内存。 */
    public long count(String correlationId, String collection) {
        return Database.inConnection("cannot count " + collection, c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    SELECT COUNT(*) FROM record WHERE correlation_id = ? AND collection = ?""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, collection);
                try (ResultSet rs = ps.executeQuery()) {
                    return rs.next() ? rs.getLong(1) : 0L;
                }
            }
        });
    }

    /**
     * 中文：查询某次预约是否已登记过并返回已有预约记录。
     * 同一预约不能被确认两次，这正是案例研究要求的防重复规则；现在由主键在数据库层保证。
     */
    public Optional<String> existingAppointment(String correlationId, String appointmentReference) {
        return Database.inConnection("cannot read the appointment index", c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    SELECT booking_id FROM appointment_index
                    WHERE correlation_id = ? AND appointment_reference = ?""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, appointmentReference);
                try (ResultSet rs = ps.executeQuery()) {
                    return rs.next() ? Optional.ofNullable(rs.getString(1)) : Optional.empty();
                }
            }
        });
    }

    /**
     * 中文：登记预约索引。保留首次写入的预约号，重复登记不会覆盖既有结果：
     * 先尝试插入，若主键已存在则数据库抛出唯一性冲突，此处按“已登记”处理并忽略。
     */
    public void indexAppointment(String correlationId, String appointmentReference, String bookingId) {
        Database.inConnection("cannot index the appointment", c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    INSERT INTO appointment_index (correlation_id, appointment_reference, booking_id)
                    VALUES (?, ?, ?)""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, appointmentReference);
                ps.setString(3, bookingId);
                ps.executeUpdate();
            } catch (SQLException e) {
                // 中文：唯一性冲突表示该预约已登记，属于预期路径而非错误，因此不向上抛出。
                if (!"23505".equals(e.getSQLState())) {
                    throw e;
                }
            }
            return null;
        });
    }

    /**
     * 中文：判断该关联下是否已存在金额与币种相同的交易。
     * 金额用容差比较而非等值比较，因为浮点累加会产生微小误差，等值判断会导致漏判重复。
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
        return Database.inConnection("cannot read the attempt count", c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    SELECT attempts FROM attempt_counter
                    WHERE correlation_id = ? AND activity = ?""")) {
                ps.setString(1, scope(correlationId));
                ps.setString(2, activity);
                try (ResultSet rs = ps.executeQuery()) {
                    return rs.next() ? rs.getInt(1) : 0;
                }
            }
        });
    }

    /**
     * 中文：把尝试次数加一并写回，返回新值；外部服务据此判断“只失败一次”的注入规则是否仍然有效。
     * 自增在一条 UPDATE 中原子完成，避免多个工作者并发重试时丢失计数；若该活动尚无记录，
     * 则插入初值 1，插入遇唯一性冲突说明并发对手已抢先建行，此时重做一次自增即可。
     */
    public int nextAttempt(String correlationId, String activity) {
        String scope = scope(correlationId);
        return Database.inConnection("cannot advance the attempt count", c -> {
            String update = """
                    UPDATE attempt_counter SET attempts = attempts + 1, recorded_at = ?
                    WHERE correlation_id = ? AND activity = ?""";
            try (PreparedStatement up = c.prepareStatement(update)) {
                up.setDate(1, Date.valueOf(LocalDate.now()));
                up.setString(2, scope);
                up.setString(3, activity);
                if (up.executeUpdate() > 0) {
                    return attempts(scope, activity);
                }
            }
            try (PreparedStatement ins = c.prepareStatement("""
                    INSERT INTO attempt_counter (correlation_id, activity, attempts, recorded_at)
                    VALUES (?, ?, 1, ?)""")) {
                ins.setString(1, scope);
                ins.setString(2, activity);
                ins.setDate(3, Date.valueOf(LocalDate.now()));
                ins.executeUpdate();
                return 1;
            } catch (SQLException conflict) {
                // 中文：并发对手已建行，重做一次自增，保证计数不丢。
                try (PreparedStatement up = c.prepareStatement(update)) {
                    up.setDate(1, Date.valueOf(LocalDate.now()));
                    up.setString(2, scope);
                    up.setString(3, activity);
                    up.executeUpdate();
                }
                return attempts(scope, activity);
            }
        });
    }

    /** 中文：清空全部记录与索引，用于测试隔离或重放演示，不建议在正常业务路径中调用。 */
    public void clear() {
        Database.inConnection("cannot clear the store", c -> {
            try (PreparedStatement ps = c.prepareStatement("DELETE FROM record")) {
                ps.executeUpdate();
            }
            try (PreparedStatement ps = c.prepareStatement("DELETE FROM appointment_index")) {
                ps.executeUpdate();
            }
            try (PreparedStatement ps = c.prepareStatement("DELETE FROM attempt_counter")) {
                ps.executeUpdate();
            }
            return null;
        });
    }

    /** 中文：把库中的 JSON 文本还原为映射；读出的数值可能是整数或小数，调用方统一用字符串形式取值。 */
    private static Map<String, Object> parse(String payload) throws Exception {
        return Database.json().readValue(payload, new TypeReference<LinkedHashMap<String, Object>>() {
        });
    }
}

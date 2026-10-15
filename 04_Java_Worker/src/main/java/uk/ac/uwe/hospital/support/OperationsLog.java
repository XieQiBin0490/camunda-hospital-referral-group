package uk.ac.uwe.hospital.support;

import com.fasterxml.jackson.core.type.TypeReference;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * An append-only audit log of what each worker did.
 *
 * <p>Requirement REQ-37 asks that audit records identify user, date, time and action, and
 * that ordinary users cannot edit them. The workers cannot settle the access-control half
 * on their own, but they can stop making it worse: every automated decision is written
 * here with the actor, the instant, the action and the correlation handle, and the log
 * exposes no update or delete operation. Review item 1 closed the other half of the gap -
 * the log used to live in a list in the process and vanished on restart; it is now a table
 * in {@link Database}, and the table is only ever appended to.
 *
 * <p>中文：这是只追加的审计日志：记录操作人、时间点、动作与关联句柄，并且刻意不提供任何
 * 更新或删除方法，也没有暴露底层集合，因此普通使用者无法篡改已写入的条目——这一点用
 * API 表面来保证，而不是靠约定。每条记录都带上关联句柄，使一次转诊全过程中的自动化决策
 * 可以被串起来复核。整改清单第 1 项补上了原先陈述的缺口：日志原先存放在进程内存的列表里，
 * 重启即失，现在改为数据库中的一张表，且该表只允许追加。
 */
public final class OperationsLog {

    /**
     * 中文：一条审计条目，字段对应需求要求的审计内容：谁、何时、做了什么，外加关联依据。
     * 其中关联句柄用于串起同一件事务的全部动作，过程实例键与元素编号用于回指具体的流程节点，
     * 明细映射承载动作相关的补充数据。
     */
    public record Entry(Instant at, String actor, String action, String correlationId,
                        long processInstanceKey, String elementId, Map<String, Object> detail) {
    }

    /** 中文：进程级单例，保证所有工作者写入同一份审计日志，序号与内容才具有全局意义。 */
    private static final OperationsLog INSTANCE = new OperationsLog();

    /** 中文：查询语句共用一份，避免在多个方法里重复书写列清单。 */
    private static final String SELECT_COLUMNS =
            "SELECT occurred_at, actor, action, correlation_id, process_instance_key, "
                    + "element_id, detail FROM audit_log";

    /** 中文：单例模式，构造器私有，避免出现互不可见的第二份审计序列。 */
    private OperationsLog() {
    }

    /** 中文：返回全局唯一日志实例，作为所有工作者共同的审计出口。 */
    public static OperationsLog get() {
        return INSTANCE;
    }

    /**
     * 中文：追加一条记录。时间点由日志自己在写入时确定，调用方无法伪造；明细先复制为不可变映射，
     * 防止调用方事后修改已归档的条目内容。
     */
    public void record(String actor, String action, String correlationId,
                       long processInstanceKey, String elementId, Map<String, Object> detail) {
        Instant at = Instant.now();
        Database.inConnection("cannot append to the audit log", c -> {
            try (PreparedStatement ps = c.prepareStatement("""
                    INSERT INTO audit_log
                      (occurred_at, actor, action, correlation_id, process_instance_key, element_id, detail)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""")) {
                ps.setTimestamp(1, Timestamp.from(at));
                ps.setString(2, actor);
                ps.setString(3, action);
                ps.setString(4, correlationId == null ? "-" : correlationId);
                ps.setLong(5, processInstanceKey);
                ps.setString(6, elementId);
                ps.setString(7, Database.json().writeValueAsString(Map.copyOf(detail)));
                ps.executeUpdate();
            }
            return null;
        });
    }

    /** 中文：返回全部条目的快照，按追加顺序排列，读取不会改变日志内容。 */
    public List<Entry> all() {
        return query(SELECT_COLUMNS + " ORDER BY seq", null);
    }

    /** 中文：按关联句柄查询条目；没有记录时返回空列表，使调用方无需额外判空。 */
    public List<Entry> forCorrelation(String correlationId) {
        return query(SELECT_COLUMNS + " WHERE correlation_id = ? ORDER BY seq",
                correlationId == null ? "-" : correlationId);
    }

    /** 中文：返回条目总数，用于测试断言与运行监控，不改变日志内容。 */
    public int size() {
        return Database.inConnection("cannot count the audit log", c -> {
            try (PreparedStatement ps = c.prepareStatement("SELECT COUNT(*) FROM audit_log");
                 ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getInt(1) : 0;
            }
        });
    }

    /** 中文：清空日志，仅供测试隔离或重放演示使用，正常业务流程不应调用。 */
    public void clear() {
        Database.inConnection("cannot clear the audit log", c -> {
            try (PreparedStatement ps = c.prepareStatement("DELETE FROM audit_log")) {
                ps.executeUpdate();
            }
            return null;
        });
    }

    /**
     * 中文：共用的查询实现。读出的明细用不可修改映射包装；这里刻意不用 Map.copyOf，
     * 因为库中可能存有原始记录里的空值，而空值会让 Map.copyOf 抛异常。
     */
    private static List<Entry> query(String sql, String correlationId) {
        return Database.inConnection("cannot read the audit log", c -> {
            List<Entry> out = new ArrayList<>();
            try (PreparedStatement ps = c.prepareStatement(sql)) {
                if (correlationId != null) {
                    ps.setString(1, correlationId);
                }
                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        Map<String, Object> detail = rs.getString(7) == null
                                ? Map.of()
                                : Database.json().readValue(rs.getString(7),
                                        new TypeReference<LinkedHashMap<String, Object>>() {
                                        });
                        out.add(new Entry(rs.getTimestamp(1).toInstant(), rs.getString(2),
                                rs.getString(3), rs.getString(4), rs.getLong(5), rs.getString(6),
                                Collections.unmodifiableMap(detail)));
                    }
                }
            }
            return List.copyOf(out);
        });
    }
}

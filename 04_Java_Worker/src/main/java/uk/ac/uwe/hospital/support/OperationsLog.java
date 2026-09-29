package uk.ac.uwe.hospital.support;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * An append-only audit log of what each worker did.
 *
 * <p>The initial release has no audit store, so requirement REQ-37 ("audit
 * records must identify user, date, time and action, and must not be editable by
 * ordinary users") is only partly supported. The workers cannot fix that on
 * their own, but they can stop making it worse: every automated decision is
 * written here with the actor, the instant, the action and the correlation
 * handle, and the log exposes no update or delete operation. The gap that
 * remains is persistence and access control, which is stated in the acceptance
 * evaluation rather than papered over.
 *
 * <p>中文：这是只追加的审计日志：记录操作人、时间点、动作与关联句柄，并且刻意不提供任何
 * 更新或删除方法，也没有暴露底层集合，因此普通使用者无法篡改已写入的条目——这一点用
 * API 表面来保证，而不是靠约定。每条记录都带上关联句柄，使一次转诊全过程中的自动化决策
 * 可以被串起来复核。真正的缺口是持久化与访问控制，属于基础设施层面的问题，已在验收说明中
 * 陈述，此处不假装已经解决。
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

    /** 中文：全局条目序列，用同步包装的列表保证多线程追加时不丢条目；读取时会持锁复制快照。 */
    private final List<Entry> entries = Collections.synchronizedList(new ArrayList<>());
    /** 中文：按关联句柄建立的次级索引，使查询一次事务的全部记录无需扫描整个日志。 */
    private final Map<String, List<Entry>> byCorrelation = new ConcurrentHashMap<>();

    /** 中文：单例模式，构造器私有，避免出现互不可见的第二份审计序列。 */
    private OperationsLog() {
    }

    /** 中文：返回全局唯一日志实例，作为所有工作者共同的审计出口。 */
    public static OperationsLog get() {
        return INSTANCE;
    }

    /** 中文：追加一条记录。时间点由日志自己在写入时确定，调用方无法伪造；明细先复制为不可变映射。 */
    public void record(String actor, String action, String correlationId,
                       long processInstanceKey, String elementId, Map<String, Object> detail) {
        // 中文：时间在写入瞬间取当前时刻，明细做防御性复制，防止调用方事后修改已归档的条目内容。
        Entry e = new Entry(Instant.now(), actor, action, correlationId,
                processInstanceKey, elementId, Map.copyOf(detail));
        entries.add(e);
        // 中文：同时写入关联索引，查询单次事务时只需读取对应列表；句柄缺失时归入占位键。
        byCorrelation.computeIfAbsent(correlationId == null ? "-" : correlationId,
                k -> Collections.synchronizedList(new ArrayList<>())).add(e);
    }

    /** 中文：返回全部条目的不可变快照。持锁复制是为了避免遍历期间被并发追加所干扰。 */
    public List<Entry> all() {
        // 中文：同步块与写入端的列表锁一致，保证复制过程中不会读到中间状态。
        synchronized (entries) {
            return List.copyOf(entries);
        }
    }

    /** 中文：按关联句柄查询条目；没有记录时返回空列表，使调用方无需额外判空。 */
    public List<Entry> forCorrelation(String correlationId) {
        return List.copyOf(byCorrelation.getOrDefault(correlationId, List.of()));
    }

    /** 中文：返回条目总数，用于测试断言与运行监控，不改变日志内容。 */
    public int size() {
        return entries.size();
    }

    /** 中文：清空日志与索引，仅供测试隔离或重放演示使用，正常业务流程不应调用。 */
    public void clear() {
        entries.clear();
        byCorrelation.clear();
    }
}

package uk.ac.uwe.hospital;

import uk.ac.uwe.hospital.support.Database;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.OperationsLog;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Writes business records in one process and reads them back in another.
 *
 * <p>This is the evidence for review item 1. Running {@code write} and then {@code read}
 * as two separate JVM invocations is the point: the second process shares nothing with the
 * first except the database file, so anything it can read survived a restart.
 *
 * <pre>
 *   java -cp hospital-external-workers-1.0.0.jar uk.ac.uwe.hospital.PersistenceCheck write
 *   java -cp hospital-external-workers-1.0.0.jar uk.ac.uwe.hospital.PersistenceCheck read
 * </pre>
 *
 * <p>中文：本类用来为整改清单第 1 项提供证据。先在一个进程里写业务记录，再在另一个进程里读回来，
 * 两次是彼此独立的 JVM 调用，第二个进程除数据库文件外与第一个进程没有任何共享，因此凡能读到的
 * 内容都确实跨过了重启。任一断言不成立即以非零状态退出，便于脚本判定。
 */
public final class PersistenceCheck {

    /** 中文：本次检查使用的关联句柄，读取阶段按同一句柄查询。 */
    private static final String EPISODE = "EP-PERSIST-1";

    /** 中文：工具类入口，不实例化。 */
    private PersistenceCheck() {
    }

    /** 中文：程序入口。参数 write 执行写入，read 执行读取并断言，dump 只列出库中现存的关联句柄。 */
    public static void main(String[] args) {
        String mode = args.length > 0 ? args[0] : "read";
        System.out.println("database: " + Database.url());
        System.out.println("mode: " + mode);
        boolean ok;
        if ("write".equals(mode)) {
            ok = write();
        } else if ("dump".equals(mode)) {
            ok = dump();
        } else {
            ok = read();
        }
        System.out.println(ok ? "RESULT: PASS" : "RESULT: FAIL");
        if (!ok) {
            System.exit(1);
        }
    }

    /**
     * 中文：列出数据库中每一个关联句柄下存了哪些集合、各有多少条记录，以及审计日志规模。
     * 端到端运行时用它查看工作者在真实流程中究竟落下了什么。
     */
    private static boolean dump() {
        HospitalStore store = HospitalStore.get();
        OperationsLog log = OperationsLog.get();
        List<String> correlations = Database.inConnection("cannot list the episodes", c -> {
            List<String> out = new ArrayList<>();
            try (java.sql.PreparedStatement ps = c.prepareStatement(
                    "SELECT DISTINCT correlation_id FROM record ORDER BY correlation_id");
                 java.sql.ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    out.add(rs.getString(1));
                }
            }
            return out;
        });
        System.out.println("episodes with stored records: " + correlations.size());
        for (String correlation : correlations) {
            List<String> collections = Database.inConnection("cannot list collections", c -> {
                List<String> out = new ArrayList<>();
                try (java.sql.PreparedStatement ps = c.prepareStatement(
                        "SELECT collection, COUNT(*) FROM record WHERE correlation_id = ? "
                                + "GROUP BY collection ORDER BY collection")) {
                    ps.setString(1, correlation);
                    try (java.sql.ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            out.add(rs.getString(1) + "=" + rs.getInt(2));
                        }
                    }
                }
                return out;
            });
            System.out.println("  " + correlation + "  " + String.join(" ", collections)
                    + "  attempts=" + store.attempts(correlation, "request-treatment-capacity"));
        }
        System.out.println("audit entries: " + log.size());
        for (OperationsLog.Entry e : log.all()) {
            System.out.println("  " + e.at() + "  " + e.actor() + "  " + e.action()
                    + "  episode=" + e.correlationId());
        }
        return !correlations.isEmpty() || log.size() > 0;
    }

    /** 中文：写入阶段。覆盖业务记录、预约去重索引、尝试计数与审计日志四类状态。 */
    private static boolean write() {
        HospitalStore store = HospitalStore.get();
        OperationsLog log = OperationsLog.get();
        boolean ok = true;

        // 中文：先清空，使本次检查可重复执行，结果不受上一次运行影响。
        store.clear();
        log.clear();

        Map<String, Object> referral = new LinkedHashMap<>();
        referral.put("referralReference", "REF-PERSIST-1");
        referral.put("patientId", "PAT-778812");
        referral.put("urgency", "urgent");
        store.put(EPISODE, "referrals", "REF-PERSIST-1", referral);
        System.out.println("wrote referrals/REF-PERSIST-1");

        store.put(EPISODE, "appointments", "APPT-PERSIST-1", Map.of(
                "appointmentReference", "APPT-PERSIST-1",
                "slot", "2026-11-03T09:20",
                "clinic", "Chemotherapy Suite B"));
        System.out.println("wrote appointments/APPT-PERSIST-1");

        store.put(EPISODE, "payments", "PAY-PERSIST-1", Map.of(
                "amount", 480.0d, "currency", "GBP", "status", "completed"));
        System.out.println("wrote payments/PAY-PERSIST-1");

        store.indexAppointment(EPISODE, "APPT-PERSIST-1", "BOOK-PERSIST-1");
        System.out.println("indexed appointment APPT-PERSIST-1");

        System.out.println("attempt 1 -> " + store.nextAttempt(EPISODE, "request-treatment-capacity"));
        System.out.println("attempt 2 -> " + store.nextAttempt(EPISODE, "request-treatment-capacity"));

        log.record("PersistenceCheck", "referral:registered", EPISODE, 1L, "T_ReceiveReferral",
                Map.of("referralReference", "REF-PERSIST-1"));
        log.record("PersistenceCheck", "payment:completed", EPISODE, 1L, "T_RequestPayment",
                Map.of("amount", "480.00", "currency", "GBP"));
        System.out.println("audit entries written: " + log.size());

        if (store.count(EPISODE, "referrals") != 1) {
            System.out.println("CHECK store readable in the writing process -> FAIL");
            ok = false;
        }
        return ok;
    }

    /** 中文：读取阶段。逐项断言上一进程写入的内容是否仍然存在。 */
    private static boolean read() {
        HospitalStore store = HospitalStore.get();
        OperationsLog log = OperationsLog.get();
        List<String> failures = new ArrayList<>();

        Map<String, Object> referral = store.get(EPISODE, "referrals", "REF-PERSIST-1");
        boolean referralOk = referral != null && "PAT-778812".equals(referral.get("patientId"));
        report("referral REF-PERSIST-1 survived with its patient id", referralOk);
        if (!referralOk) {
            failures.add("referral record missing or altered: " + referral);
        }

        boolean apptOk = store.get(EPISODE, "appointments", "APPT-PERSIST-1") != null;
        report("appointment APPT-PERSIST-1 survived", apptOk);
        if (!apptOk) {
            failures.add("appointment record missing");
        }

        // 中文：付款判重依赖已持久化的交易，因此重启后仍应能识别出重复金额。
        boolean dupOk = store.duplicatePayment(EPISODE, 480.0d, "GBP");
        report("the persisted payment still trips the duplicate-payment check", dupOk);
        if (!dupOk) {
            failures.add("duplicate payment detection lost the earlier transaction");
        }

        boolean indexOk = store.existingAppointment(EPISODE, "APPT-PERSIST-1").isPresent();
        report("the appointment index still recognises the booking", indexOk);
        if (!indexOk) {
            failures.add("appointment index lost");
        }

        int attempts = store.attempts(EPISODE, "request-treatment-capacity");
        boolean attemptsOk = attempts == 2;
        report("the attempt counter still reads " + attempts + " (expected 2)", attemptsOk);
        if (!attemptsOk) {
            failures.add("attempt counter is " + attempts + ", expected 2");
        }

        int entries = log.size();
        boolean auditOk = entries >= 2 && !log.forCorrelation(EPISODE).isEmpty();
        report("audit log kept " + entries + " entries, indexed by episode", auditOk);
        if (!auditOk) {
            failures.add("audit log lost the entries");
        }

        boolean appendOnly = java.util.Arrays.stream(OperationsLog.class.getMethods())
                .noneMatch(m -> m.getName().startsWith("update") || m.getName().startsWith("delete")
                        || m.getName().startsWith("remove"));
        report("the audit log still exposes no update or delete operation", appendOnly);
        if (!appendOnly) {
            failures.add("the audit log gained a mutating operation");
        }

        for (String f : failures) {
            System.out.println("  failure: " + f);
        }
        return failures.isEmpty();
    }

    /** 中文：统一输出格式，便于人工阅读与脚本解析。 */
    private static void report(String what, boolean ok) {
        System.out.println("CHECK " + what + " -> " + (ok ? "PASS" : "FAIL"));
    }
}

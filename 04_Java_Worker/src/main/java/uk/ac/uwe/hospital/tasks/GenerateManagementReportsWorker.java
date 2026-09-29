package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.OperationsLog;

import java.time.Instant;
import java.time.YearMonth;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * {@code generate-management-reports} - produces the referral, waiting-time,
 * contact-attempt and delayed-letter figures the Administrative Management Team
 * asks for.
 *
 * <p>This job type is bound in {@code S3} to the management reporting process,
 * which was deployed but is not part of the initial release's operational scope,
 * so the worker's other purpose matters more than its output: it is the one place
 * where the audit entries the other workers write are aggregated and read back.
 * That is the closest the build comes to the "auditable relationship between
 * patient, referral, treatment request, appointment, funding decision, payment
 * and refund" that REQ-44 asks for, and the acceptance evaluation states plainly
 * that the full correlation view is still missing.
 *
 * <p>中文：本类服务于 BPMN 中"生成管理报表"的 Zeebe 服务任务，作业类型为
 * {@code generate-management-reports}，在 S3 中绑定到管理报表流程。该流程已部署但不在首版
 * 运行范围内，因此本工人更重要的价值在于：它是唯一把其他工人写下的审计条目汇总并读回的地方，
 * 也是 REQ-44 所要求"患者—转诊—治疗申请—预约—拨款—付款—退款"可审计关联的最近似实现。
 * 报表数据源全部来自内部审计日志与存储统计，不引入新的患者敏感数据。
 */
public class GenerateManagementReportsWorker extends AbstractWorker {

    /** 中文：BPMN 服务任务绑定的作业类型，必须与模型中 zeebe:taskDefinition 的 type 完全一致。 */
    public static final String JOB_TYPE = "generate-management-reports";

    public GenerateManagementReportsWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"生成管理报表"作业。统计审计条目数量并调用模拟报表服务，
     * 把结果整理成 reportFigures 结构写回流程变量；episodeId 为 all 时给出整体口径。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：reportPeriod 默认取当前年月，episodeId 默认"all"表示跨就诊的全量口径；
        // 指定具体就诊编号时，报表才追加该次就诊的业务计数。
        String period = ctx.findString("reportPeriod").orElse(YearMonth.now().toString());
        String episodeId = ctx.findString("episodeId").orElse("all");

        // 中文：审计条目是报表的可信数据源：全量口径取日志总条数，
        // 单次就诊口径取按 correlation 归集的条数，这正是 REQ-44 关联视图的落点。
        OperationsLog logStore = OperationsLog.get();
        int audited = episodeId.equals("all") ? logStore.size() : logStore.forCorrelation(episodeId).size();

        // 中文：外部报表服务为模拟实现，只负责签发报表凭证，真实统计值由本工人自行汇总。
        String reference = ExternalServices.Reporting.generate(period);

        // 中文：用 LinkedHashMap 固定字段顺序，便于报表输出与对账时逐项比对；
        // 前四项是引擎侧自动活动的运行指标（完成、重试、报错），用于观察工人健康度。
        Map<String, Object> figures = new LinkedHashMap<>();
        figures.put("auditedActivities", audited);
        figures.put("completedAutomatedActivities", AbstractWorker.completed());
        figures.put("retriedAutomatedActivities", AbstractWorker.failed());
        figures.put("rejectedAutomatedActivities", AbstractWorker.errored());
        if (!episodeId.equals("all")) {
            // 中文：只有单次就诊口径才统计容量尝试、付款与信件投递数量，
            // 这些数字来自 HospitalStore，用于支撑报告里的运营与财务指标。
            figures.put("capacityAttempts", HospitalStore.get().attempts(episodeId, JOB_TYPE));
            figures.put("paymentTransactions", HospitalStore.get().count(episodeId, "payments"));
            figures.put("correspondenceDispatched", HospitalStore.get().count(episodeId, "letters")
                    + HospitalStore.get().count(episodeId, "correspondence"));
        }

        // 中文：一次性写回报表凭证、口径、统计图和生成时间；reportGenerated 供流程网关判断
        // 报表是否成功产出，reportFigures 供后续节点展示或归档。
        ctx.setAll(Map.of(
                "episodeId", episodeId,
                "reportGenerated", true,
                "reportReference", reference,
                "reportPeriod", period,
                "reportFigures", figures,
                "reportGeneratedAt", Instant.now().toString()))
           .note("generated report " + reference + " for " + period + " over " + audited + " audit entries");
    }
}

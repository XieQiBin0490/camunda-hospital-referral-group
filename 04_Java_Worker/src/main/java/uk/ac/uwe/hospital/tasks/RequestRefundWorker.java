package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.Map;

/**
 * {@code request-refund} - asks the external Payment Service Provider to return
 * money for a cancelled, postponed or changed treatment.
 *
 * <p>The authority for this activity is financial, not clinical: the case study
 * says clinical staff may provide information about the treatment decision but
 * must not approve financial refunds unless they also hold the required
 * financial authority. The worker therefore acts only on a refund the Finance
 * Team has already authorised, and it will only refund against a transaction it
 * can see in the episode - a refund with no original payment is refused rather
 * than issued, which is what stops the same charge being returned twice.
 *
 * <p>中文：本类服务于 BPMN 中"申请退款"的 Zeebe 服务任务，作业类型为 {@code request-refund}，
 * 处理的是治疗取消、延期或变更后的退款环节。它的权限来源是财务而非临床：
 * 只有财务团队已授权的退款才会真正发起，临床人员提供的治疗决策信息不能当作付款授权。
 * 同时要求本次就诊下必须能查到对应的原始交易，避免同一笔收费被重复退回。
 */
public class RequestRefundWorker extends AbstractWorker {

    /** 中文：BPMN 服务任务绑定的作业类型，必须与模型中 zeebe:taskDefinition 的 type 完全一致。 */
    public static final String JOB_TYPE = "request-refund";

    public RequestRefundWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"申请退款"作业。两道前置校验（财务授权、存在原始交易）任一不通过即拒绝退款，
     * 只有都通过才调用外部支付服务，并把 refundStatus 等结果写回流程变量供网关分流。
     */
    @Override
    protected void handle(JobContext ctx) {
        String patientId = ctx.requireString("patientId");
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));
        // 中文：退款金额优先取 refundAmount，退化到 paymentAmount，都没有时按 0 处理，不凭空估算金额。
        double amount = ctx.doubleOr("refundAmount", ctx.doubleOr("paymentAmount", 0.0d));
        // 中文：paymentReference 为本次退款要冲抵的原始交易凭证，缺失时置空串以便后续判断。
        String original = ctx.findString("paymentReference").orElse("");

        // 中文：refundAuthorised 是财务团队授权留痕，默认 false 表示"未授权即拒绝"的安全默认值。
        // hasOriginal 有两重来源：本次就诊已登记的 payments 记录，或流程变量里直接给出的原始凭证。
        boolean authorised = ctx.bool("refundAuthorised", false);
        boolean hasOriginal = !HospitalStore.get().list(episodeId, "payments").isEmpty()
                || !original.isBlank();

        if (!authorised) {
            // 中文：缺少财务授权属于业务性拒绝而非系统故障，因此正常完成作业并写入阻止原因，
            // 让流程按"未授权"分支流转到人工处理，而不是抛异常触发无意义重试。
            ctx.set("episodeId", episodeId)
               .set("refundStatus", "not authorised")
               .set("refundBlockedReason", "no financial authority recorded for this refund")
               .note("refund refused: the Finance Team has not authorised it");
            return;
        }
        if (!hasOriginal) {
            // 中文：查不到原始交易说明这次退款没有可冲抵的收费，直接拒绝可防止重复退款，
            // 与授权拦截一样按业务结果返回，而不是当作外部系统故障重试。
            ctx.set("episodeId", episodeId)
               .set("refundStatus", "no matching payment")
               .set("refundBlockedReason", "no original transaction found against the episode")
               .note("refund refused: nothing to refund against");
            return;
        }

        // 中文：调用外部支付服务发起退款（模拟实现）；原始凭证缺失时用 "-" 占位，
        // 因为此处已通过 hasOriginal 校验，说明交易记录存在，只是变量里没直接给出凭证。
        ExternalServices.Payment.RefundResult result =
                ExternalServices.Payment.refund(amount, original.isBlank() ? "-" : original);

        // 中文：refundStatus 是流程网关依赖的关键输出（refunded / rejected），
        // 必须与外部服务返回的 approved 标志保持一致，不能由本地推断。
        ctx.set("episodeId", episodeId)
           .set("refundStatus", result.approved() ? "refunded" : "rejected")
           .set("refundAmount", amount)
           .set("refundOriginalReference", original)
           .set("refundProcessedAt", Instant.now().toString());
        if (result.approved()) {
            // 中文：只有服务商确认退款后才登记退款单，避免留下"看似成功"的假记录；
            // 落库内容仅含凭证、金额和原始交易号，足以支撑对账与审计。
            ctx.set("refundReference", result.reference())
               .note("refund " + result.reference() + " issued for " + amount);
            HospitalStore.get().put(episodeId, "refunds", result.reference(), Map.of(
                    "reference", result.reference(), "amount", amount, "original", original));
        } else {
            // 中文：服务商明确拒绝（拒付）是确定的业务结果，不是暂时性故障，
            // 因此只留痕不抛异常，交由后续人工或网关分支跟进，避免无谓的自动重试。
            ctx.note("provider rejected the refund of " + amount);
        }
    }
}

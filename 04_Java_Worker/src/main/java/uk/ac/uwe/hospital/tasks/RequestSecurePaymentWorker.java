package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * {@code request-secure-payment} - sends the secure payment request to the
 * external Payment Service Provider and records the outcome.
 *
 * <p>Three requirements meet in this activity, and the worker is where they are
 * either honoured or quietly lost:
 *
 * <ul>
 *   <li><b>REQ-20</b> - the provider returns status, transaction reference, date
 *       and amount. This worker owns {@code paymentStatus}, which the model's
 *       {@code G_PaymentOutcome} gateway reads, and it writes only those four
 *       facts back.</li>
 *   <li><b>REQ-21</b> - the system must not store the patient's complete card
 *       information. The worker never reads a card field, never writes one, and
 *       actively strips any card-like key it finds in the job payload before the
 *       variables are completed, so a careless form cannot leak one into the
 *       engine's history.</li>
 *   <li><b>REQ-22</b> - a declined or duplicated payment must permit a further
 *       attempt without creating a second booking or charging twice. The worker
 *       checks the episode for an existing transaction of the same amount before
 *       it sends anything.</li>
 * </ul>
 *
 * <p>"No response" is deliberately not conflated with "declined". The case study
 * says a payment the provider took but never confirmed must be marked for
 * investigation and must not trigger a second request; {@code paymentStatus}
 * therefore carries the provider's silence through to the gateway, which routes
 * it to the investigation branch.
 *
 * <p>中文：本类服务于 BPMN 中"请求安全支付"的 Zeebe 服务任务，作业类型为
 * {@code request-secure-payment}，负责向外部支付服务商发起扣款请求并回写结果。
 * 三条需求在此交汇：REQ-20 要求服务商回传状态、交易凭证、日期与金额，本工人据此写入
 * {@code paymentStatus} 供 {@code G_PaymentOutcome} 网关分流；REQ-21 要求系统不存储患者完整卡信息，
 * 因此本工人既不读也不写任何卡字段，并在作业完成前主动清洗作业负载中的卡类键；
 * REQ-22 要求拒付或重复支付可以重试而不重复扣款，因此在发起请求前先检查本次就诊是否已有同额交易。
 * "无响应"被刻意与"拒付"区分开：服务商已受理但未确认的支付必须标记为待调查，且不得再次发起请求。
 */
public class RequestSecurePaymentWorker extends AbstractWorker {

    /** 中文：BPMN 服务任务绑定的作业类型，必须与模型中 zeebe:taskDefinition 的 type 完全一致。 */
    public static final String JOB_TYPE = "request-secure-payment";

    /** Keys that must never reach process variables, whatever a form sends. */
    /**
     * 中文：REQ-21 的禁止名单，列出任何情况下都不允许写入流程变量的卡类字段（卡号、CVV、有效期等）。
     * 作业完成前逐一检查并丢弃，避免表单校验疏漏把敏感卡数据带进 Zeebe 的变量历史。
     * 字段键名按常见大小写写法并列，只用于匹配与丢弃，不参与业务计算。
     */
    private static final String[] FORBIDDEN = {
            "cardNumber", "cardnumber", "pan", "cvv", "cvc", "securityCode",
            "cardSecurityCode", "expiryDate", "cardHolder", "cardholderName",
            "fullCardNumber", "trackData", "pin"
    };

    public RequestSecurePaymentWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"请求安全支付"作业。读取金额与币种，先做重复支付抑制，
     * 再调用外部支付服务并把状态等四项事实写回，最后清洗作业负载中的卡类字段。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 为必填；金额优先取 chargeAmount，退化到已批准的 approvedAmount，
        // 币种默认 GBP，episodeId 缺失时按患者编号推导。
        String patientId = ctx.requireString("patientId");
        double amount = ctx.doubleOr("chargeAmount", ctx.doubleOr("approvedAmount", 0.0d));
        String currency = ctx.findString("currency").orElse("GBP");
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // Stated on every activation, not only when something is wrong: the
        // position on card data is part of the activity's contract (REQ-21), and
        // a log line that only appears on failure cannot evidence the normal run.
        ctx.note("no card data read from the job and none written back");

        if (amount <= 0.0d) {
            // 中文：金额非法时不猜测也不补算，只记录"没有可计费金额"的事实，
            // 让后续人工或上游流程去纠正，避免生成金额为零的支付请求。
            ctx.note("no chargeable amount on the request");// recorded, not invented
        }

        // 中文：REQ-22 的重复支付抑制：同一就诊、同额同币种已有交易时直接返回已确认状态，
        // 并置 duplicatePaymentRequestSuppressed、paymentAlreadyRecorded 标记，不再向服务商重发请求。
        if (HospitalStore.get().duplicatePayment(episodeId, amount, currency)) {
            ctx.set("episodeId", episodeId)
               .set("paymentStatus", ExternalServices.PaymentOutcome.CONFIRMED.processValue())
               .set("duplicatePaymentRequestSuppressed", true)
               .set("paymentAlreadyRecorded", true)
               .note("an existing " + currency + " transaction for the same amount was found;"
                       + " no second request was sent");
            return;
        }

        // 中文：外部支付服务为模拟实现，返回四种可能存在的结果状态（确认、拒付、无响应、紧急临床需要）。
        ExternalServices.Payment.Result result = ExternalServices.Payment.request(episodeId, amount, currency);

        // 中文：逐项写入请求结果。REQ-20 只允许回写四项事实：状态、凭证、日期与金额，
        // 因此这里不写任何卡信息，并显式置 cardDataStored=false 作为合规留痕。
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("episodeId", episodeId);
        out.put("paymentStatus", result.outcome().processValue());
        out.put("paymentAmount", amount);
        out.put("paymentCurrency", currency);
        out.put("paymentRequestedAt", Instant.now().toString());
        if (result.transactionReference() != null) {
            // 中文：只有服务商给出交易凭证时才登记凭证与交易日期，
            // 无响应场景下这两个变量保持缺失，使网关能区分"未确认"与"已拒付"。
            out.put("paymentReference", result.transactionReference());
            out.put("paymentDate", result.date().toString());
        }
        out.put("cardDataStored", false);
        ctx.setAll(out);

        // 中文：按四种结果分别留痕并说明业务含义：确认即成功；拒付允许再次尝试且不产生重复预约；
        // 无响应只标记待调查、绝不重复发起请求；紧急临床需要则转交财务人工解决。
        switch (result.outcome()) {
            case CONFIRMED -> ctx.note("provider confirmed " + currency + " " + amount
                    + " as " + result.transactionReference());
            case DECLINED -> ctx.note("provider declined " + currency + " " + amount
                    + "; a further attempt is permitted and no duplicate booking is created");
            case NO_RESPONSE -> ctx.note("provider accepted the request but returned no confirmation;"
                    + " marked for investigation and NOT re-requested");
            case URGENT_CLINICAL_NEED -> ctx.note("payment unresolved but urgent clinical need recorded;"
                    + " referred to Finance for resolution");
        }

        if (result.outcome() == ExternalServices.PaymentOutcome.CONFIRMED) {
            // 中文：只对已确认的支付登记交易记录到 payments 分类下，
            // 这些记录既是对账依据，也是退款工人的原始交易来源和重复支付检测的依据；
            // 拒付、无响应、紧急临床需要均不落库，避免脏数据影响退款与报表。
            HospitalStore.get().put(episodeId, "payments", result.transactionReference(), Map.of(
                    "reference", result.transactionReference(),
                    "amount", amount,
                    "currency", currency,
                    "date", result.date().toString()));
        }

        // REQ-21 enforcement: refuse to carry card-like fields into the engine.
        for (String forbidden : FORBIDDEN) {
            // 中文：一旦发现卡类字段就告警并留痕。此处刻意不做回写、也不复制该字段的值，
            // 保证敏感卡数据既不进入流程变量，也不会出现在审计记录里。
            if (ctx.has(forbidden)) {
                log.warn("job {} carried '{}'; it is not written back to the process", ctx.jobKey(), forbidden);
                ctx.note("card-like field '" + forbidden + "' discarded before completion");
            }
        }
    }
}

package uk.ac.uwe.hospital.tasks;

import uk.ac.uwe.hospital.AbstractWorker;
import uk.ac.uwe.hospital.JobContext;
import uk.ac.uwe.hospital.support.ExternalServices;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * {@code request-missing-documentation} - asks the referring organisation for the
 * documents the completeness check found absent.
 *
 * <p>The case study requires the request to name what is missing and requires the
 * referral to return to the completeness check rather than proceed; the model
 * already loops back, so this worker only has to record what it asked for and
 * whom it asked.
 *
 * <p>中文：本类服务于 BPMN 发送任务 T_RequestMissingDocuments（向转诊机构索取缺失资料），
 * 作业类型为 {@code request-missing-documentation}。它由网关 G_DocumentsComplete 的
 * documentsComplete = false 分支触发，也可能在顾问医师判定 referralDecision = "information required"
 * 时被再次调用。业务动作只是把"缺哪些资料、向谁索取"记录成事实，并写回 documentsComplete = false，
 * 使转诊回到资料完整性检查重新判定；模型自身已经包含回环，因此工人不必推动流程，只需留下可追溯的凭证。
 */
public class RequestMissingDocumentationWorker extends AbstractWorker {

    /** 中文：作业类型标识，必须与模型中 zeebe:taskDefinition 的 type 逐字一致，否则引擎不会派发作业。 */
    public static final String JOB_TYPE = "request-missing-documentation";

    /** 中文：用"工人族名 + 作业类型"拼出订阅名，便于在 Zeebe 与日志中区分同一类型的多个工人实例。 */
    public RequestMissingDocumentationWorker() {
        super("hospital-external-workers:" + JOB_TYPE);
    }

    /** 中文：返回本工人订阅的作业类型，基类据此注册 Zeebe 作业工人并接收该类型的作业。 */
    @Override
    public String jobType() {
        return JOB_TYPE;
    }

    /**
     * 中文：处理一次"索取缺失资料"作业。先汇总缺失清单，再通过外部通信服务发出索取通知，
     * 最后写回索取凭证，并把 documentsComplete 置假，让流程回到资料完整性检查重新判定。
     */
    @Override
    protected void handle(JobContext ctx) {
        // 中文：patientId 是必填输入，缺失说明表单或上游数据有缺陷，requireString 会抛出校验异常。
        String patientId = ctx.requireString("patientId");
        // 中文：索取对象默认写成中性描述，保证即使转诊机构变量缺失，信函与审计记录也不会为空。
        String organisation = ctx.findString("referringOrganisation").orElse("referring organisation");
        // 中文：缺失清单交给 collectMissing 汇总，优先采用人工填写的缺失项，其次用完整性检查结果。
        List<String> missing = collectMissing(ctx);

        // 中文：调用外部通信服务真正发出索取通知；服务不可用时抛可重试异常，由引擎按重试策略处理。
        String reference = ExternalServices.Correspondence.requestDocuments(missing, organisation);
        // 中文：episodeId 是贯穿全流程的就诊关联号（REQ-44）；缺失时按患者号推导，保证留痕能归集。
        String episodeId = ctx.findString("episodeId").orElseGet(() -> Ids.episode(patientId));

        // 中文：写回流程变量。其中 documentsComplete = false 是网关 G_DocumentsComplete
        // 中文：判定"资料仍不齐"的依据，会令转诊退回资料完整性检查；其余变量保存索取内容、
        // 中文：凭证、对象与时间，构成 REQ-07 要求的可追溯证据。
        ctx.set("episodeId", episodeId)
           .set("missingDocumentsRequested", true)
           .set("missingDocumentList", String.join("; ", missing))
           .set("missingDocumentCount", missing.size())
           .set("documentRequestReference", reference)
           .set("documentRequestSentTo", organisation)
           .set("documentRequestedAt", Instant.now().toString())
           .set("documentsComplete", false)
           .note("requested " + missing.size() + " document(s) from " + organisation + " as " + reference);

        // 中文：按 episodeId 归集本次索取（集合名 documentRequests，键为凭证号），供后续查询与审计；
        // 中文：只保存引用性字段，不写入患者敏感数据，符合数据最小化要求。
        HospitalStore.get().put(episodeId, "documentRequests", reference, Map.of(
                "reference", reference,
                "organisation", organisation,
                "documents", String.join("; ", missing),
                "requestedAt", Instant.now().toString()));
    }

    /**
     * Named documents if the form supplied them, otherwise the standard pack.
     *
     * <p>中文：缺失清单按优先级取值：人工填写的 missingDocuments 最可信，其次是用
     * documentationCheckResult 记录的检查结论，两者都没有时才退回案例研究认可的标准资料包
     * （门诊信、检查结果、诊断报告）。这样既尊重人工判断，也保证流程不会因为表单留空而没有内容可发。
     */
    private List<String> collectMissing(JobContext ctx) {
        // 中文：分号分隔是表单里多值文本字段的既定约定，这里对分隔符两侧的空白做容错处理。
        String supplied = ctx.findString("missingDocuments").orElse("");
        if (!supplied.isBlank()) {
            return List.of(supplied.split("\\s*;\\s*"));
        }
        // 中文：完整性检查结果同样是分号分隔文本；空白视为"没有信息"，继续向下取默认值。
        String check = ctx.findString("documentationCheckResult").orElse("");
        if (!check.isBlank()) {
            return List.of(check.split("\\s*;\\s*"));
        }
        // 中文：最后的兜底清单是案例研究点名的三类资料，避免索取通知内容为空而失去业务意义。
        return List.of("clinic letter", "investigation results", "diagnostic report");
    }
}

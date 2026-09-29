package uk.ac.uwe.hospital;

import io.camunda.zeebe.client.ZeebeClient;
import io.camunda.zeebe.client.api.response.ActivatedJob;
import io.camunda.zeebe.client.api.worker.JobClient;
import io.camunda.zeebe.client.api.worker.JobWorker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import uk.ac.uwe.hospital.support.FailureInjection;
import uk.ac.uwe.hospital.support.HospitalStore;
import uk.ac.uwe.hospital.support.Ids;
import uk.ac.uwe.hospital.support.OperationsLog;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Shared behaviour for every job worker: the one place that decides how a
 * failure reaches the engine.
 *
 * <pre>
 *   ValidationException   -&gt; throw BPMN error INVALID_JOB_INPUT
 *                             (a defect in the data or the form, not an outage)
 *   BpmnErrorException    -&gt; throw the named BPMN error, so a boundary event can catch it
 *   TransientJobException -&gt; fail the job with one fewer retry, so the engine retries
 *   anything else         -&gt; fail with no retries left: an incident, which is the
 *                             correct signal for a defect the team must look at
 * </pre>
 *
 * <p>Every completion writes housekeeping variables, files an audit entry under
 * the episode correlation, and refuses to let a worker overwrite a variable the
 * worker did not mean to write - the variable-to-branch contract on these
 * models is narrow, and widening it silently would break the gateways.
 *
 * <p>中文：这是全部外部作业工作器的公共基类，也是“一次失败如何到达引擎”的唯一决策点。</p>
 * <p>中文：把异常类型到引擎动作的映射集中在一处，是为了让具体工作器只关心业务逻辑，
 * 不必各自判断该重试、该抛 BPMN 错误，还是该留下一条需要人工处理的 incident。</p>
 * <p>中文：每次成功完成都会写入 lastAutomatedActivity 与 lastAutomatedAt 两个簿记变量，
 * 并按 episodeId 归集审计记录，从而支持事后对账与问题追溯。</p>
 * <p>中文：工作器只有显式写出的变量才会随完成命令回传，避免误覆盖网关所依赖的流程变量；
 * 模型上“变量到分支”的契约很窄，静默放宽会直接改变路由结果。</p>
 */
public abstract class AbstractWorker {

    /** 中文：用 getClass() 创建日志器，子类无需重复声明就能得到正确的日志类别。 */
    protected final Logger log = LoggerFactory.getLogger(getClass());

    // 中文：三个静态计数器用 AtomicLong，保证多工作线程下自增的原子性与可见性。
    /** 中文：成功完成的作业数，关闭时用它打印整批作业的汇总。 */
    private static final AtomicLong COMPLETED = new AtomicLong();
    /** 中文：以失败或稍后重试结束的作业数，不含业务拒绝那一类。 */
    private static final AtomicLong FAILED = new AtomicLong();
    /** 中文：被判定为输入非法或业务错误的作业数，即没有重试意义的那一类。 */
    private static final AtomicLong ERRORS = new AtomicLong();

    /** 中文：已注册到 Zeebe 客户端的作业工作器句柄，close 时据此撤销订阅。 */
    private JobWorker worker;
    /** 中文：订阅时使用的名称，用于在日志与审计中区分同一作业类型的不同实例。 */
    private final String workerName;

    /** 中文：只接收工作器名称；它同时作为订阅名，便于在引擎与日志中识别本工作器。 */
    protected AbstractWorker(String workerName) {
        this.workerName = workerName;
    }

    /**
     * The job type this worker subscribes to; it must match the model exactly.
     *
     * <p>中文：返回值必须与 BPMN 服务任务的 taskDefinition type 逐字一致，
     * 否则作业无人订阅，实例会一直停在那个活动上。</p>
     */
    public abstract String jobType();

    /**
     * Do the work and write the outputs the model branches on.
     *
     * <p>中文：子类在这里读取输入、调用外部系统，并把网关需要的输出写回 JobContext；
     * 失败语义由基类统一裁决，子类只需抛出约定的异常类型。</p>
     */
    protected abstract void handle(JobContext ctx);

    /** 中文：向引擎注册订阅并立即开始轮询；同一个工作器实例只应打开一次。 */
    public final void open(ZeebeClient client, WorkerConfig config) {
        // The builder is a three-step chain: jobType -> handler -> everything else.
        // 中文：maxJobsActive 限制本地预取的作业数，timeout 是作业锁租约（应大于最慢一次
        // 处理耗时，否则作业会在处理途中被引擎重新激活），pollInterval 决定空闲时的长轮询节奏。
        this.worker = client.newWorker()
                .jobType(jobType())
                .handler(this::onJob)
                .name(workerName)
                .maxJobsActive(config.maxJobsActive())
                .timeout(config.jobTimeout())
                .pollInterval(config.pollInterval())
                .open();
        log.info("subscribed {} as '{}'", jobType(), workerName);
    }

    /** 中文：撤销订阅并停止拉取新作业；由关闭钩子调用，因此必须容忍尚未打开的情况。 */
    public final void close() {
        // 中文：null 判断兼容“还没 open 或 open 失败”的场景，避免关闭阶段再抛异常。
        if (worker != null) {
            worker.close();
        }
    }

    /** 中文：引擎回调入口，把一次作业执行的结果翻译成对引擎的四种应答之一。 */
    private void onJob(JobClient jobClient, ActivatedJob job) {
        // 中文：先把作业快照成上下文对象，后续的读取与写出都基于这份不可变快照。
        JobContext ctx = new JobContext(job.getType(), job.getKey(), job.getProcessInstanceKey(),
                job.getElementId(), job.getRetries(), job.getVariablesAsMap());
        // 中文：用 nanoTime 计时，避免系统时钟回拨导致耗时出现负值。
        long started = System.nanoTime();
        try {
            // 中文：故障注入点，只在演示配置下抛错，用来演练重试与 incident 两条路径。
            FailureInjection.check(jobType());
            handle(ctx);
            // 中文：复制一份输出再补写簿记变量，避免污染 JobContext 内部的待写视图。
            Map<String, Object> out = new LinkedHashMap<>(ctx.outputs());
            // 中文：这两个变量是流程监控与审计的锚点，每完成一个自动化活动都会刷新。
            out.put("lastAutomatedActivity", job.getElementId());
            out.put("lastAutomatedAt", Instant.now().toString());
            // 中文：send().join() 同步等待引擎确认，保证返回时本地与引擎的状态已经一致。
            jobClient.newCompleteCommand(job.getKey()).variables(out).send().join();
            COMPLETED.incrementAndGet();
            audit(ctx, "completed", out);
            log.info("{} {} element={} instance={} -> completed in {} ms {}",
                    jobType(), job.getKey(), job.getElementId(), job.getProcessInstanceKey(),
                    (System.nanoTime() - started) / 1_000_000, ctx.notes());
        // 中文：catch 的先后顺序不可调整：越具体的异常必须越靠前，否则会被兜底分支吞掉。
        } catch (ValidationException e) {
            ERRORS.incrementAndGet();
            // 中文：错误消息里带上缺失字段名，让运维不必翻代码就知道是哪份表单出了问题。
            String message = e.getMessage() + " " + e.missingFields();
            log.warn("{} {} rejected: {}", jobType(), job.getKey(), message);
            // 中文：用固定的 INVALID_JOB_INPUT 错误码抛出，模型可据此走人工补录分支。
            jobClient.newThrowErrorCommand(job.getKey())
                    .errorCode("INVALID_JOB_INPUT")
                    .errorMessage(message)
                    .send().join();
            audit(ctx, "rejected", Map.of("errorCode", "INVALID_JOB_INPUT", "message", message));
        } catch (BpmnErrorException e) {
            ERRORS.incrementAndGet();
            log.warn("{} {} threw BPMN error {}: {}", jobType(), job.getKey(), e.errorCode(), e.getMessage());
            // 中文：沿用业务方给出的错误码，命中的是模型里对应的边界事件而非通用异常路径。
            jobClient.newThrowErrorCommand(job.getKey())
                    .errorCode(e.errorCode())
                    .errorMessage(e.getMessage())
                    .send().join();
            audit(ctx, "bpmn-error", Map.of("errorCode", e.errorCode(), "message", e.getMessage()));
        } catch (TransientJobException e) {
            FAILED.incrementAndGet();
            // 中文：重试次数在这里显式递减并用 0 兜底，避免出现负数再由引擎纠正。
            int retries = Math.max(0, job.getRetries() - 1);
            log.warn("{} {} transient failure ({} retries left): {}", jobType(), job.getKey(), retries, e.getMessage());
            // 中文：用 fail 而不是 throwError，让作业按重试语义重新激活，业务上仍可继续。
            jobClient.newFailCommand(job.getKey())
                    .retries(retries)
                    .errorMessage(e.getMessage())
                    .send().join();
            audit(ctx, "retry", Map.of("retriesLeft", retries, "message", e.getMessage()));
        } catch (RuntimeException e) {
            FAILED.incrementAndGet();
            // 中文：兜底捕获未预期的运行时异常，说明代码本身有缺陷，需要人工介入而非自动重试。
            log.error("{} {} unexpected failure", jobType(), job.getKey(), e);
            jobClient.newFailCommand(job.getKey())
                    // 中文：重试次数置 0，让引擎直接产生 incident，把问题暴露给团队。
                    .retries(0)
                    .errorMessage(e.getClass().getSimpleName() + ": " + e.getMessage())
                    .send().join();
            audit(ctx, "failed", Map.of("error", String.valueOf(e.getMessage())));
        }
    }

    /** 中文：把一次作业结果写入审计日志与病例库，作为引擎之外的可追溯记录。 */
    private void audit(JobContext ctx, String action, Map<String, Object> detail) {
        // 中文：优先使用流程中已有的 episodeId；缺失时用 patientId 推导，保证记录仍可归集。
        String correlation = ctx.findString("episodeId")
                .orElseGet(() -> Ids.episode(ctx.findString("patientId").orElse(null)));
        // 中文：动作名拼成 jobType:action，便于在日志中按作业类型聚合与统计。
        OperationsLog.get().record(workerName, jobType() + ":" + action, correlation,
                ctx.processInstanceKey(), ctx.elementId(), detail);
        // 中文：这里同步累加尝试次数，使重试在引擎之外也留有一份可核对的计数。
        HospitalStore.get().nextAttempt(correlation, jobType());
    }

    /** 中文：成功完成的作业总数，供关闭钩子打印整批作业的汇总。 */
    public static long completed() {
        return COMPLETED.get();
    }

    /** 中文：以失败或重试结束的作业总数，与“业务拒绝”分开统计以便区分故障性质。 */
    public static long failed() {
        return FAILED.get();
    }

    /** 中文：被判定为输入非法或业务错误的作业总数，正常运行时应当保持较低水位。 */
    public static long errored() {
        return ERRORS.get();
    }
}

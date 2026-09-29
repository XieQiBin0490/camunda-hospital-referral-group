package uk.ac.uwe.hospital;

import io.camunda.zeebe.client.ZeebeClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import uk.ac.uwe.hospital.support.FailureInjection;
import uk.ac.uwe.hospital.support.MessagePublisher;
import uk.ac.uwe.hospital.tasks.DistributeClinicalCorrespondenceWorker;
import uk.ac.uwe.hospital.tasks.GenerateManagementReportsWorker;
import uk.ac.uwe.hospital.tasks.PublishPatientReferralWorker;
import uk.ac.uwe.hospital.tasks.QueryAvailableAppointmentSlotsWorker;
import uk.ac.uwe.hospital.tasks.RedirectReferralWorker;
import uk.ac.uwe.hospital.tasks.RequestBloodTestWorker;
import uk.ac.uwe.hospital.tasks.RequestMissingDocumentationWorker;
import uk.ac.uwe.hospital.tasks.RequestRefundWorker;
import uk.ac.uwe.hospital.tasks.RequestSecurePaymentWorker;
import uk.ac.uwe.hospital.tasks.RequestTreatmentCapacityWorker;
import uk.ac.uwe.hospital.tasks.SendAppointmentConfirmationLetterWorker;
import uk.ac.uwe.hospital.tasks.SendReferralOutcomeWorker;
import uk.ac.uwe.hospital.tasks.SubmitPatientReferralWorker;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;

/**
 * Starts the external job workers for the hospital process definitions.
 *
 * <p>One worker per job type, and the job types are the ones the BPMN actually
 * declares: an activity whose type has no subscriber simply parks, which is the
 * most common way a Camunda 8 process "hangs" on a demo machine. {@link #verify}
 * therefore refuses to start if the fleet and the declared set disagree.
 *
 * <p>Usage:
 * <pre>
 *   mvn clean package
 *   java -jar target/hospital-external-workers-1.0.0.jar
 * </pre>
 *
 * <p>中文：外部作业工作器进程的启动入口，负责装配配置、创建 Zeebe 客户端并注册全部工作器。</p>
 * <p>中文：作业类型必须与 BPMN 中服务任务声明的类型逐一对应；没有订阅者的作业会永远停在
 * 该活动上，这正是 Camunda 8 流程在演示环境中最常见的“卡住”原因，所以启动前必须校验覆盖。</p>
 * <p>中文：覆盖校验失败时直接抛异常终止启动，宁可起不来，也不要留下一个只订阅了部分作业的进程。</p>
 */
public final class WorkersApplication {

    private static final Logger log = LoggerFactory.getLogger(WorkersApplication.class);

    /**
     * Every job type declared by the four delivered models.
     *
     * <p>中文：四个已交付 BPMN 模型中出现的全部作业类型，是启动覆盖校验的基准清单。</p>
     * <p>中文：列表顺序与文档中的活动顺序保持一致，便于人工核对与差异排查。</p>
     */
    public static final List<String> DECLARED_JOB_TYPES = List.of(
            "request-missing-documentation",
            "send-referral-outcome",
            "redirect-referral",
            "query-available-appointment-slots",
            "send-appointment-confirmation-letter",
            "request-treatment-capacity",
            "request-secure-payment",
            "distribute-clinical-correspondence",
            "request-blood-test",
            "request-refund",
            "generate-management-reports",
            // 中文：下面两个类型来自协作中的第二个可执行池 PR_ReferringOrganisation。
            // 中文：它们不是医院侧的活动，而是转诊机构侧"拟制转诊"与"发出转诊"两个作业；
            // 中文：消息抛出事件在引擎里就是作业，所以跨池消息同样必须有订阅者。
            "referring-org-submit-patient-referral",
            "referring-org-publish-patient-referral");

    /** 中文：私有构造，表明这是只提供静态入口的工具类，不会被实例化。 */
    private WorkersApplication() {
    }

    /** 中文：主流程：装配配置、建客户端、注册工作器、校验覆盖，然后阻塞等待进程退出。 */
    public static void main(String[] args) throws InterruptedException {
        WorkerConfig config = WorkerConfig.load();
        // 中文：故障注入必须先于任何订阅完成配置，否则工作器拿不到演练规则。
        FailureInjection.configure(config);

        log.info("hospital external workers starting: {}", config.describe());

        // 中文：默认值挂在客户端构建器上，单个工作器仍可在 open 时覆盖自己的参数。
        io.camunda.zeebe.client.ZeebeClientBuilder builder = ZeebeClient.newClientBuilder()
                .gatewayAddress(config.gatewayAddress())
                .defaultJobWorkerMaxJobsActive(config.maxJobsActive())
                .defaultJobTimeout(config.jobTimeout())
                .defaultJobPollInterval(config.pollInterval())
                .numJobWorkerExecutionThreads(config.workerThreads());
        if (config.plaintext()) {
            // c8run and docker-compose listen on plaintext gRPC; SaaS needs TLS.
            // 中文：只有显式配置为明文时才关闭 TLS，避免误把 SaaS 端点降级为不安全连接。
            builder = builder.usePlaintext();
        }
        ZeebeClient client = builder.build();

        // 中文：把同一个客户端交给消息发布器，使消息抛出事件对应的工作器能够真正发出跨池消息。
        // 中文：必须在任何工作器开始订阅之前完成绑定，否则早期作业会以"无客户端"降级处理。
        MessagePublisher.use(client);

        List<AbstractWorker> workers = List.of(
                new RequestMissingDocumentationWorker(),
                new SendReferralOutcomeWorker(),
                new RedirectReferralWorker(),
                new QueryAvailableAppointmentSlotsWorker(),
                new SendAppointmentConfirmationLetterWorker(),
                new RequestTreatmentCapacityWorker(),
                new RequestSecurePaymentWorker(),
                new DistributeClinicalCorrespondenceWorker(),
                new RequestBloodTestWorker(),
                new RequestRefundWorker(),
                new GenerateManagementReportsWorker(),
                // 中文：转诊机构池的两个工作器，构成跨池消息交互的发端。
                new SubmitPatientReferralWorker(),
                new PublishPatientReferralWorker());

        // 中文：用 LinkedHashMap 建立类型到工作器的索引，保持注册顺序以便校验日志可读。
        Map<String, AbstractWorker> byType = new LinkedHashMap<>();
        for (AbstractWorker w : workers) {
            byType.put(w.jobType(), w);
        }
        // 中文：先校验再订阅，保证不会出现“订阅到一半才发现缺工作器”的中间状态。
        verify(byType);

        for (AbstractWorker w : workers) {
            w.open(client, config);
        }

        // 中文：注册关闭钩子，保证 Ctrl+C 或容器停止时先撤销订阅，再关闭客户端。
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            log.info("shutting down: {} automated activities completed, {} retried, {} rejected",
                    AbstractWorker.completed(), AbstractWorker.failed(), AbstractWorker.errored());
            // 中文：一并汇报跨池消息的发布情况：0 条说明两个池之间其实没有发生任何交互，
            // 中文：这在演示"跨池消息"时正是最需要被一眼看出的异常。
            log.info("cross-pool messages: {} published, {} failed or refused",
                    MessagePublisher.published(), MessagePublisher.failed());
            workers.forEach(AbstractWorker::close);
            client.close();
        }, "hpas-workers-shutdown"));

        log.info("{} workers subscribed and polling {}", workers.size(), config.gatewayAddress());
        // 中文：计数为 1 且永不倒数，用最简单的方式让主线程常驻；轮询在工作器自己的线程上。
        new CountDownLatch(1).await();
    }

    /**
     * Fail fast if the fleet and the declared job types disagree.
     *
     * <p>中文：启动前的覆盖校验：模型声明的每个作业类型都必须有订阅者，否则实例会停住。</p>
     * <p>中文：缺订阅者属于致命错误，直接抛异常；多出的订阅者只告警，因为它不影响流程推进。</p>
     */
    private static void verify(Map<String, AbstractWorker> byType) {
        // 中文：模型要求但无人订阅的类型，正是会导致流程卡死的那一类问题。
        List<String> missing = DECLARED_JOB_TYPES.stream()
                .filter(t -> !byType.containsKey(t))
                .toList();
        // 中文：有订阅者但模型里没有的类型，通常是工作器先于模型交付，属于可容忍的偏差。
        List<String> extra = byType.keySet().stream()
                .filter(t -> !DECLARED_JOB_TYPES.contains(t))
                .toList();
        if (!missing.isEmpty()) {
            throw new IllegalStateException("no worker subscribes to declared job type(s): " + missing);
        }
        if (!extra.isEmpty()) {
            log.warn("workers subscribe to job type(s) no delivered model declares: {}", extra);
        }
        log.info("job type coverage verified: {} of {} declared types have a subscriber",
                DECLARED_JOB_TYPES.size() - missing.size(), DECLARED_JOB_TYPES.size());
    }
}

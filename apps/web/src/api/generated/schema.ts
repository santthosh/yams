export interface paths {
  "/api/v1/data/assets": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Assets */
    get: operations["assets_api_v1_data_assets_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/data/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Health */
    get: operations["health_api_v1_data_health_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/data/refresh": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Refresh */
    post: operations["refresh_api_v1_data_refresh_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/data/snapshots": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Snapshots */
    get: operations["snapshots_api_v1_data_snapshots_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/experiments": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Experiments */
    get: operations["list_experiments_api_v1_experiments_get"];
    put?: never;
    /** Create */
    post: operations["create_api_v1_experiments_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/experiments/{experiment_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations["read_api_v1_experiments__experiment_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/experiments/{experiment_id}/series": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Series */
    get: operations["series_api_v1_experiments__experiment_id__series_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/experiments/{experiment_id}/trades": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Trades */
    get: operations["trades_api_v1_experiments__experiment_id__trades_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/forecasts/{forecast_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations["read_api_v1_forecasts__forecast_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/health": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Health */
    get: operations["health_api_v1_health_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/jobs/{job_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Get Job */
    get: operations["get_job_api_v1_jobs__job_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/jobs/{job_id}/cancel": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Cancel Job */
    post: operations["cancel_job_api_v1_jobs__job_id__cancel_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/portfolios": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Accounts */
    get: operations["accounts_api_v1_portfolios_get"];
    put?: never;
    /** Create */
    post: operations["create_api_v1_portfolios_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/portfolios/{portfolio_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Detail */
    get: operations["detail_api_v1_portfolios__portfolio_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/portfolios/{portfolio_id}/recommendations": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** List Recommendations */
    get: operations["list_recommendations_api_v1_portfolios__portfolio_id__recommendations_get"];
    put?: never;
    /** Create */
    post: operations["create_api_v1_portfolios__portfolio_id__recommendations_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/portfolios/{portfolio_id}/transactions": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Transactions */
    get: operations["transactions_api_v1_portfolios__portfolio_id__transactions_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/recommendations/{recommendation_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations["read_api_v1_recommendations__recommendation_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/strategies": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Strategies */
    get: operations["strategies_api_v1_strategies_get"];
    put?: never;
    /** Create */
    post: operations["create_api_v1_strategies_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/strategies/{strategy_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Detail */
    get: operations["detail_api_v1_strategies__strategy_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/strategies/{strategy_id}/versions": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Versions */
    get: operations["versions_api_v1_strategies__strategy_id__versions_get"];
    put?: never;
    /** Publish */
    post: operations["publish_api_v1_strategies__strategy_id__versions_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/strategy-evaluations": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Create */
    post: operations["create_api_v1_strategy_evaluations_post"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/strategy-evaluations/{evaluation_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations["read_api_v1_strategy_evaluations__evaluation_id__get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/workspace": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Workspace */
    get: operations["workspace_api_v1_workspace_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/livez": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Liveness
     * @description Process liveness only: not database, fixture or worker readiness.
     */
    get: operations["liveness_livez_get"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** ActionEvidence */
    ActionEvidence: {
      /** Current Weight */
      current_weight: string;
      /** Position Cap */
      position_cap: string | null;
    };
    /** Alias */
    Alias: {
      /** Asset Id */
      asset_id: string;
      /**
       * Available At
       * Format: date-time
       */
      available_at: string;
      /**
       * Effective From
       * Format: date
       */
      effective_from: string;
      /** Effective To Exclusive */
      effective_to_exclusive: string | null;
      /**
       * Ingested At
       * Format: date-time
       */
      ingested_at: string;
      /** Provider */
      provider: string;
      /** Provider Id */
      provider_id: string;
      /** Symbol */
      symbol: string;
      /** Venue */
      venue: string;
    };
    /** AllocationExclusion */
    AllocationExclusion: {
      /** Asset Id */
      asset_id: string;
      /** Reason */
      reason: string;
    };
    /** AllocationTarget */
    AllocationTarget: {
      /** Asset Id */
      asset_id: string;
      /** Sector */
      sector: string;
      /** Weight */
      weight: string;
    };
    /** AppliedAction */
    AppliedAction: {
      /** Key */
      key: string;
      /** Payload Sha256 */
      payload_sha256: string;
    };
    /** ArtifactReference */
    ArtifactReference: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Schema Version */
      schema_version: number;
      /** Sha256 */
      sha256: string;
    };
    /** AssetContext */
    AssetContext: {
      /** Aliases */
      aliases: components["schemas"]["Alias"][];
      /** Fundamentals */
      fundamentals: components["schemas"]["Fundamental"][];
      /**
       * Schema Version
       * @constant
       */
      schema_version: 2;
      /** Sectors */
      sectors: components["schemas"]["Sector"][];
    };
    /** AssetPageV1 */
    AssetPageV1: {
      /** Items */
      items: components["schemas"]["AssetV1"][];
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /** Next Cursor */
      next_cursor: string | null;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
    };
    /** AssetV1 */
    AssetV1: {
      /** Asset Id */
      asset_id: string;
      /**
       * Currency
       * @constant
       */
      currency: "USD";
      /**
       * Instrument
       * @enum {string}
       */
      instrument: "ordinary_equity" | "etf";
      /** Provider */
      provider: string;
      /** Provider Id */
      provider_id: string;
      /** Sector */
      sector: string;
      /** Symbol */
      symbol: string;
      /** Venue */
      venue: string;
    };
    /** Calendar */
    Calendar: {
      /** Generator Version */
      generator_version: string;
      /** Id */
      id: string;
      /** Label */
      label: string;
      /** Limitations */
      limitations: string[];
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      /** Sessions */
      sessions: components["schemas"]["Session"][];
      /**
       * Timezone
       * @constant
       */
      timezone: "America/New_York";
      /** Timezone Rules Version */
      timezone_rules_version: string;
    };
    /** CalendarReference */
    CalendarReference: {
      /** Artifact Path */
      artifact_path: string;
      /** Id */
      id: string;
      /**
       * Timezone
       * @constant
       */
      timezone: "America/New_York";
      /** Version */
      version: string;
    };
    /** CandidateEvidence */
    CandidateEvidence: {
      /** Asset Id */
      asset_id: string;
      /** Contributions */
      contributions: components["schemas"]["FeatureValue"][];
      /** Exclusion Reasons */
      exclusion_reasons: string[];
      /** Features */
      features: components["schemas"]["FeatureValue"][];
      /** Score */
      score: number | null;
    };
    /** ComparisonTerms */
    ComparisonTerms: {
      /** Benchmark Asset Id */
      benchmark_asset_id: string;
      /** Calendar Sha256 */
      calendar_sha256: string;
      /** Core Engine Version */
      core_engine_version: string;
      /**
       * Core Policy Version
       * @constant
       */
      core_policy_version: "walk_forward_v1";
      /**
       * End Session Exclusive
       * Format: date
       */
      end_session_exclusive: string;
      evaluation_split: components["schemas"]["EvaluationSplit"];
      execution_policy: components["schemas"]["backend__portfolio__execution__ExecutionPolicy"];
      /** Holdout Start Session */
      holdout_start_session: string | null;
      /** Initial Capital Usd */
      initial_capital_usd: string;
      /** Reporting Engine Version */
      reporting_engine_version: string;
      /**
       * Reporting Version
       * @default q12_v1
       * @constant
       */
      reporting_version: "q12_v1";
      /** Sessions */
      sessions: string[];
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Source Mode
       * @enum {string}
       */
      source_mode: "synthetic_fixture" | "research_market_data";
      /**
       * Start Session
       * Format: date
       */
      start_session: string;
      /** Universe Canonical Json */
      universe_canonical_json: string;
    };
    /** DataDiagnosticEvidence */
    DataDiagnosticEvidence: {
      /** Asset Id */
      asset_id: string | null;
      /** Count */
      count: number;
      /** Reason */
      reason: string;
      /** Session Date */
      session_date: string | null;
    };
    /** DataHealthV1 */
    DataHealthV1: {
      /**
       * Checked At
       * Format: date-time
       */
      checked_at: string;
      current_snapshot: components["schemas"]["SnapshotV1"] | null;
      /**
       * Freshness
       * @enum {string}
       */
      freshness: "synthetic" | "unknown" | "refresh_failed";
      latest_job: components["schemas"]["JobV1"] | null;
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /**
       * Status
       * @enum {string}
       */
      status: "empty" | "ready" | "refreshing" | "failed";
      /** Warnings */
      warnings: string[];
    };
    /** DividendEntitlement */
    DividendEntitlement: {
      /** Asset Id */
      asset_id: string;
      /** Evidence Sha256 */
      evidence_sha256: string;
      /**
       * Ex Session
       * Format: date
       */
      ex_session: string;
      /** Key */
      key: string;
      /** Per Share */
      per_share: string;
      /** Quantity */
      quantity: string;
    };
    /** ErrorDetail */
    ErrorDetail: {
      /**
       * Code
       * @enum {string}
       */
      code:
        | "VALIDATION_ERROR"
        | "NOT_FOUND"
        | "METHOD_NOT_ALLOWED"
        | "HTTP_ERROR"
        | "NOT_READY"
        | "STATE_CONFLICT"
        | "IDEMPOTENCY_CONFLICT"
        | "STALE_DATA"
        | "INSUFFICIENT_MARKET_DATA"
        | "LIMIT_EXCEEDED"
        | "PROVIDER_UNAVAILABLE"
        | "FORECAST_UNAVAILABLE"
        | "JOB_FAILED"
        | "INTERNAL_ERROR"
        | "WORKLOAD_LIMIT"
        | "RESOURCE_EXHAUSTED"
        | "TIME_LIMIT";
      /**
       * Correlation Id
       * Format: uuid
       */
      correlation_id: string;
      /** Details */
      details: {
        [key: string]: string | number | boolean | string[];
      };
      /** Message */
      message: string;
      /** Retryable */
      retryable: boolean;
    };
    /** ErrorEnvelope */
    ErrorEnvelope: {
      error: components["schemas"]["ErrorDetail"];
    };
    /**
     * EvaluationCandidateV1
     * @description Shared engine fields, uniquely named in the generated public schema.
     */
    EvaluationCandidateV1: {
      /** Allocation Eligible */
      allocation_eligible: boolean;
      /** Asset Id */
      asset_id: string;
      /** Eligible */
      eligible: boolean;
      /** Features */
      features:
        | components["schemas"]["FeatureValues"]
        | components["schemas"]["MeanReversionFeatures"]
        | components["schemas"]["LowVolatilityFeatures"]
        | null;
      /** Input Sha256 */
      input_sha256: string;
      /** Median Dollar Volume */
      median_dollar_volume: string | null;
      /** Rank */
      rank: number | null;
      /** Raw Close */
      raw_close: string | null;
      /** Reasons */
      reasons: string[];
      /** Scoring */
      scoring:
        | components["schemas"]["ScoreEvidence"]
        | components["schemas"]["MeanReversionScore"]
        | components["schemas"]["LowVolatilityScore"]
        | null;
      /** Sector */
      sector: string | null;
      /** Trend Sma */
      trend_sma: string | null;
    };
    /** EvaluationReproducibilityV1 */
    EvaluationReproducibilityV1: {
      /** Calendar Sha256 */
      calendar_sha256: string;
      /** Config Sha256 */
      config_sha256: string;
      /** Engine Version */
      engine_version: string;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** EvaluationSplit */
    EvaluationSplit: {
      /** Holdout Fraction */
      holdout_fraction: number;
      /**
       * Kind
       * @constant
       */
      kind: "chronological";
    };
    /** ExecutionContext */
    ExecutionContext: {
      /**
       * Approved At
       * Format: date-time
       */
      approved_at: string;
      /** Calendar Sha256 */
      calendar_sha256: string;
      /**
       * Decision Cutoff
       * Format: date-time
       */
      decision_cutoff: string;
      /**
       * Decision Session
       * Format: date
       */
      decision_session: string;
      /** Engine Version */
      engine_version: string;
      /**
       * Execution Mode
       * @enum {string}
       */
      execution_mode: "current_paper" | "historical_replay";
      /**
       * Execution Snapshot Id
       * @default null
       */
      execution_snapshot_id: string | null;
      /**
       * Execution Snapshot Sha256
       * @default null
       */
      execution_snapshot_sha256: string | null;
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
    };
    /** ExperimentAccepted */
    ExperimentAccepted: {
      /**
       * Experiment Id
       * Format: uuid
       */
      experiment_id: string;
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
    };
    /** ExperimentBenchmarkSummaryV1 */
    ExperimentBenchmarkSummaryV1: {
      /** Asset Id */
      asset_id: string;
      /** Available */
      available: boolean;
      periods: components["schemas"]["MetricsPeriods"] | null;
      /** Unavailable Reason */
      unavailable_reason: string | null;
      /** Warnings */
      warnings: string[];
    };
    /** ExperimentCurvePointV1 */
    ExperimentCurvePointV1: {
      /** Benchmark Nav Usd */
      benchmark_nav_usd: string | null;
      /** Benchmark Unavailable Reason */
      benchmark_unavailable_reason: string | null;
      /** Cash Baseline Nav Usd */
      cash_baseline_nav_usd: string;
      /** Cash Usd */
      cash_usd: string;
      cash_weight: components["schemas"]["WeightValue"];
      /**
       * Currency
       * @default USD
       * @constant
       */
      currency: "USD";
      drawdown_fraction: components["schemas"]["MetricValue"];
      max_position_weight: components["schemas"]["WeightValue"];
      /**
       * Phase
       * @enum {string}
       */
      phase: "development" | "holdout";
      /** Portfolio Nav Usd */
      portfolio_nav_usd: string;
      /** Positions */
      positions: components["schemas"]["Position"][];
      /**
       * Session Date
       * Format: date
       */
      session_date: string;
    };
    /** ExperimentDetailV1 */
    ExperimentDetailV1: {
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Currency
       * @default USD
       * @constant
       */
      currency: "USD";
      curve_artifact: components["schemas"]["ArtifactReference"] | null;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /** Engine Version */
      engine_version: string;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["ExperimentRequest"];
      /** Inputs Canonical Json */
      inputs_canonical_json: string;
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      metrics: components["schemas"]["ExperimentMetrics"] | null;
      /** Provider */
      provider: string;
      report: components["schemas"]["ExperimentReportSummaryV1"] | null;
      reproducibility_manifest:
        components["schemas"]["ArtifactReference"] | null;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
      strategy_config: components["schemas"]["StrategyConfigV1"];
      trade_artifact: components["schemas"]["ArtifactReference"] | null;
      /** Warnings */
      warnings: string[];
    };
    /** ExperimentMetrics */
    ExperimentMetrics: {
      annualized_return_fraction: components["schemas"]["MetricValue"];
      annualized_volatility_fraction: components["schemas"]["MetricValue"];
      cumulative_return_fraction: components["schemas"]["MetricValue"];
      /** Fees Usd */
      fees_usd: string;
      max_drawdown_fraction: components["schemas"]["MetricValue"];
      sharpe_ratio: components["schemas"]["MetricValue"];
      /** Slippage Usd */
      slippage_usd: string;
      /** Trade Count */
      trade_count: number;
      turnover_fraction: components["schemas"]["MetricValue"];
    };
    /** ExperimentPageV1 */
    ExperimentPageV1: {
      /** Items */
      items: components["schemas"]["ExperimentSummaryV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** ExperimentReportSummaryV1 */
    ExperimentReportSummaryV1: {
      benchmark: components["schemas"]["ExperimentBenchmarkSummaryV1"];
      cash: components["schemas"]["MetricsPeriods"];
      comparison: components["schemas"]["ComparisonTerms"];
      /** Comparison Sha256 */
      comparison_sha256: string;
      /** Core Manifest Sha256 */
      core_manifest_sha256: string;
      portfolio: components["schemas"]["MetricsPeriods"];
      /** Reporting Engine Version */
      reporting_engine_version: string;
      /**
       * Reporting Version
       * @constant
       */
      reporting_version: "q12_v1";
      /** Warnings */
      warnings: string[];
    };
    /** ExperimentReproducibilityV1 */
    ExperimentReproducibilityV1: {
      /** Calendar Sha256 */
      calendar_sha256: string;
      /** Config Sha256 */
      config_sha256: string;
      /** Core Manifest Sha256 */
      core_manifest_sha256: string;
      /**
       * Core Policy Version
       * @constant
       */
      core_policy_version: "walk_forward_v1";
      /**
       * Decision Clock Policy
       * @constant
       */
      decision_clock_policy: "next_pinned_open_minus_one_hour";
      /** Engine Version */
      engine_version: string;
      inputs: components["schemas"]["ExperimentRequest"];
      /** Provider */
      provider: string;
      /** Reporting Engine Version */
      reporting_engine_version: string;
      /**
       * Reporting Version
       * @constant
       */
      reporting_version: "q12_v1";
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      schema_version: 1;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Source Mode
       * @enum {string}
       */
      source_mode: "synthetic_fixture" | "research_market_data";
      strategy_config: components["schemas"]["StrategyConfigV1"];
      /** Warnings */
      warnings: string[];
    };
    /** ExperimentRequest */
    ExperimentRequest: {
      /** Benchmark Asset Id */
      benchmark_asset_id: string;
      /**
       * End Session Exclusive
       * Format: date
       */
      end_session_exclusive: string;
      evaluation_split: components["schemas"]["EvaluationSplit"];
      /**
       * Execution Policy Id
       * @constant
       */
      execution_policy_id: "us_eod_next_open_v1";
      /** Initial Capital Usd */
      initial_capital_usd: string;
      /** Random Seed */
      random_seed: number;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /**
       * Start Session
       * Format: date
       */
      start_session: string;
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** ExperimentRunV1 */
    ExperimentRunV1: {
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      curve_artifact: components["schemas"]["ArtifactReference"] | null;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /** Engine Version */
      engine_version: string;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["ExperimentRequest"];
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      metrics: components["schemas"]["ExperimentMetrics"] | null;
      reproducibility_manifest:
        components["schemas"]["ArtifactReference"] | null;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
      trade_artifact: components["schemas"]["ArtifactReference"] | null;
      /** Warnings */
      warnings: string[];
    };
    /** ExperimentSeriesPageV1 */
    ExperimentSeriesPageV1: {
      /** Items */
      items: components["schemas"]["ExperimentCurvePointV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** ExperimentSummaryV1 */
    ExperimentSummaryV1: {
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /** Engine Version */
      engine_version: string;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["ExperimentRequest"];
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
    };
    /** ExperimentTradeV1 */
    ExperimentTradeV1: {
      context: components["schemas"]["ExecutionContext"];
      /**
       * Currency
       * @default USD
       * @constant
       */
      currency: "USD";
      eligible_session: components["schemas"]["Session"];
      fill: components["schemas"]["FillEffect"] | null;
      /** Filled Quantity */
      filled_quantity: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      order: components["schemas"]["OrderIntent"];
      /** Pending Quantity */
      pending_quantity: string;
      policy: components["schemas"]["backend__portfolio__execution__ExecutionPolicy"];
      /** Reason */
      reason: string | null;
      /** Skipped Quantity */
      skipped_quantity: string;
      state_after: components["schemas"]["PortfolioState"];
      /**
       * Status
       * @enum {string}
       */
      status: "pending" | "skipped" | "filled" | "partially_filled";
      /** Terminal */
      terminal: boolean;
    };
    /** ExperimentTradesPageV1 */
    ExperimentTradesPageV1: {
      /** Items */
      items: components["schemas"]["ExperimentTradeV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** FeatureValue */
    FeatureValue: {
      /** Name */
      name: string;
      /** Unavailable Reason */
      unavailable_reason: string | null;
      /** Value */
      value: number | null;
    };
    /** FeatureValues */
    FeatureValues: {
      /** Momentum Long */
      momentum_long: number;
      /** Momentum Short */
      momentum_short: number;
      /** Volatility */
      volatility: number;
    };
    /** FillEffect */
    FillEffect: {
      /** Cash Delta Usd */
      cash_delta_usd: string;
      /** Commission Usd */
      commission_usd: string;
      /**
       * Evidence Available At
       * Format: date-time
       */
      evidence_available_at: string;
      /** Executed Price */
      executed_price: string;
      /**
       * Execution At
       * Format: date-time
       */
      execution_at: string;
      /**
       * Execution Session
       * Format: date
       */
      execution_session: string;
      /** Gross Usd */
      gross_usd: string;
      /**
       * Proposed At
       * Format: date-time
       */
      proposed_at: string;
      /** Quantity */
      quantity: string;
      /** Raw Price */
      raw_price: string;
      /** Realized Pnl Usd */
      realized_pnl_usd: string;
      /** Removed Basis Usd */
      removed_basis_usd: string;
      /** Slippage Usd */
      slippage_usd: string;
    };
    /** FixtureMetadata */
    FixtureMetadata: {
      /** Asset Count */
      asset_count: number;
      /**
       * First Session
       * Format: date
       */
      first_session: string;
      /**
       * Label
       * @constant
       */
      label: "SYNTHETIC_DATA_ONLY";
      /**
       * Last Session
       * Format: date
       */
      last_session: string;
      /** Manifest Sha256 */
      manifest_sha256: string;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
    };
    /** ForecastAllocation */
    ForecastAllocation: {
      /** Cash Weight */
      cash_weight: string;
      /** Upfront Cost Usd */
      upfront_cost_usd: string | null;
      /** Weights */
      weights: components["schemas"]["ForecastWeight"][];
    };
    /** ForecastOutcome */
    ForecastOutcome: {
      /** Median Ending Value Usd */
      median_ending_value_usd: string;
      /** Median Return Fraction */
      median_return_fraction: number;
      /** P10 Return Fraction */
      p10_return_fraction: number;
      /** P90 Return Fraction */
      p90_return_fraction: number;
      /** Probability Of Loss */
      probability_of_loss: number;
    };
    /** ForecastV1 */
    ForecastV1: {
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /** Block Length Sessions */
      block_length_sessions: number;
      /** Calendar Version */
      calendar_version: string | null;
      /** Cash Return Fraction */
      cash_return_fraction: number;
      /**
       * Comparability
       * @constant
       */
      comparability: "common_shock_paths";
      current_allocation: components["schemas"]["ForecastAllocation"];
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /**
       * Decision Cutoff Utc
       * Format: date-time
       */
      decision_cutoff_utc: string;
      /** Engine Version */
      engine_version: string;
      /** Fingerprint */
      fingerprint: string | null;
      /** Fingerprint Schema Version */
      fingerprint_schema_version: number;
      /** Future Sessions */
      future_sessions: string[] | null;
      hold_unchanged: components["schemas"]["ForecastOutcome"] | null;
      /** Horizon Calendar Days */
      horizon_calendar_days: number;
      /** Horizon End At */
      horizon_end_at: string | null;
      /** Horizon Trading Sessions */
      horizon_trading_sessions: number | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Initial Value Usd */
      initial_value_usd: string | null;
      /** Input Array Sha256 */
      input_array_sha256: string | null;
      /** Limitations */
      limitations: string[];
      /** Lookback Sessions */
      lookback_sessions: number;
      /** Median Return Delta Fraction */
      median_return_delta_fraction: number | null;
      /**
       * Method
       * @constant
       */
      method: "multivariate_block_bootstrap_v1";
      proposed: components["schemas"]["ForecastOutcome"] | null;
      proposed_allocation: components["schemas"]["ForecastAllocation"];
      rng: components["schemas"]["RNGMetadata"];
      sampled_indices: components["schemas"]["ArtifactReference"] | null;
      /** Seed */
      seed: number;
      /** Simulation Count */
      simulation_count: number;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status: "available" | "unavailable";
      /** Unavailable Reason */
      unavailable_reason: string | null;
    };
    /** ForecastWeight */
    ForecastWeight: {
      /** Asset Id */
      asset_id: string;
      /** Weight */
      weight: string;
    };
    /** Fundamental */
    Fundamental: {
      /** Asset Id */
      asset_id: string;
      /**
       * Available At
       * Format: date-time
       */
      available_at: string;
      /**
       * Ingested At
       * Format: date-time
       */
      ingested_at: string;
      /** Metric */
      metric: string;
      /**
       * Period End
       * Format: date
       */
      period_end: string;
      /** Provider */
      provider: string;
      /** Value */
      value: string;
    };
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components["schemas"]["ValidationError"][];
    };
    /** HealthV1 */
    HealthV1: {
      database: components["schemas"]["ReadinessCheck"];
      fixture_metadata: components["schemas"]["FixtureMetadata"] | null;
      fixtures: components["schemas"]["ReadinessCheck"];
      migration: components["schemas"]["ReadinessCheck"];
      /**
       * Paper Only
       * @default true
       * @constant
       */
      paper_only: true;
      /**
       * Status
       * @enum {string}
       */
      status: "ready" | "not_ready";
      workspace: components["schemas"]["ReadinessCheck"];
    };
    /**
     * JobCancelRequest
     * @description Explicit empty JSON command; extra fields are forbidden.
     */
    JobCancelRequest: Record<string, never>;
    /** JobResult */
    JobResult: {
      /**
       * Kind
       * @enum {string}
       */
      kind: "diagnostic" | "resource";
      /** Message */
      message: string;
      /** Resource Id */
      resource_id: string | null;
    };
    /** JobV1 */
    JobV1: {
      /** Attempts */
      attempts: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Kind */
      kind: string;
      /** Max Attempts */
      max_attempts: number;
      /** Progress */
      progress: number;
      result: components["schemas"]["JobResult"] | null;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    JsonValue: unknown;
    /** Liveness */
    Liveness: {
      /**
       * Paper Only
       * @default true
       * @constant
       */
      paper_only: true;
      /**
       * Status
       * @default alive
       * @constant
       */
      status: "alive";
    };
    /** LowVolatilityFeatures */
    LowVolatilityFeatures: {
      /**
       * Kind
       * @constant
       */
      kind: "low_volatility";
      /** Volatility */
      volatility: number;
    };
    /** LowVolatilityScore */
    LowVolatilityScore: {
      /**
       * Kind
       * @constant
       */
      kind: "low_volatility";
      /** Score */
      score: number;
      /** Volatility Z */
      volatility_z: number;
    };
    /** LowVolatilitySignalConfig */
    LowVolatilitySignalConfig: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      kind: "low_volatility";
      /** Require Positive Trend */
      require_positive_trend: boolean;
      /** Trend Sma Sessions */
      trend_sma_sessions: number;
      /** Volatility Sessions */
      volatility_sessions: number;
    };
    /** MarketBarV1 */
    MarketBarV1: {
      /** Adjusted Close */
      adjusted_close: string;
      /** Asset Id */
      asset_id: string;
      /**
       * Availability Basis
       * @enum {string}
       */
      availability_basis: "published" | "observed" | "synthetic";
      /**
       * Available At
       * Format: date-time
       */
      available_at: string;
      /** Close */
      close: string;
      /**
       * Currency
       * @constant
       */
      currency: "USD";
      /** High */
      high: string;
      /**
       * Ingested At
       * Format: date-time
       */
      ingested_at: string;
      /** Low */
      low: string;
      /** Open */
      open: string;
      /**
       * Price Basis
       * @enum {string}
       */
      price_basis: "raw_as_traded" | "provider_unverified";
      /** Provider */
      provider: string;
      /** Published At */
      published_at: string | null;
      /** Quality Flags */
      quality_flags: string[];
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      /**
       * Session Date
       * Format: date
       */
      session_date: string;
      /** Volume */
      volume: number;
      /** Volume Basis */
      volume_basis: string;
    };
    /** MeanReversionFeatures */
    MeanReversionFeatures: {
      /**
       * Kind
       * @constant
       */
      kind: "mean_reversion";
      /** Mean Reversion Distance */
      mean_reversion_distance: number;
      /** Mean Reversion Sma */
      mean_reversion_sma: string;
      /** Volatility */
      volatility: number;
    };
    /** MeanReversionScore */
    MeanReversionScore: {
      /**
       * Kind
       * @constant
       */
      kind: "mean_reversion";
      /** Mean Reversion Z */
      mean_reversion_z: number;
      /** Score */
      score: number;
    };
    /** MeanReversionSignalConfig */
    MeanReversionSignalConfig: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      kind: "mean_reversion";
      /** Mean Reversion Sessions */
      mean_reversion_sessions: number;
      /** Require Positive Trend */
      require_positive_trend: boolean;
      /** Trend Sma Sessions */
      trend_sma_sessions: number;
      /** Volatility Sessions */
      volatility_sessions: number;
    };
    /** MetricValue */
    MetricValue: {
      /** Unavailable Reason */
      unavailable_reason: string | null;
      /** Value */
      value: number | null;
    };
    /** MetricsPeriods */
    MetricsPeriods: {
      development: components["schemas"]["PeriodMetrics"];
      holdout: components["schemas"]["PeriodMetrics"];
      total: components["schemas"]["PeriodMetrics"];
    };
    /** MissingSession */
    MissingSession: {
      /** Asset Id */
      asset_id: string;
      /**
       * Session Date
       * Format: date
       */
      session_date: string;
    };
    /** OrderIntent */
    OrderIntent: {
      /** Asset Id */
      asset_id: string;
      /** Key */
      key: string;
      /** Requested Quantity */
      requested_quantity: string;
      /** Sector */
      sector: string;
      /**
       * Side
       * @enum {string}
       */
      side: "BUY" | "SELL";
    };
    /** PageRequest */
    PageRequest: {
      /**
       * Cursor
       * @default null
       */
      cursor: string | null;
      /**
       * Limit
       * @default 25
       */
      limit: number;
    };
    /** Page[PaperPortfolioV1] */
    Page_PaperPortfolioV1_: {
      /** Items */
      items: components["schemas"]["PaperPortfolioV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** Page[SnapshotV1] */
    Page_SnapshotV1_: {
      /** Items */
      items: components["schemas"]["SnapshotV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** Page[StrategyV1] */
    Page_StrategyV1_: {
      /** Items */
      items: components["schemas"]["StrategyV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** Page[StrategyVersionV1] */
    Page_StrategyVersionV1_: {
      /** Items */
      items: components["schemas"]["StrategyVersionV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** PaperOrderBatchV1 */
    PaperOrderBatchV1: {
      /**
       * Approval Idempotency Key
       * Format: uuid
       */
      approval_idempotency_key: string;
      /**
       * Approved At
       * Format: date-time
       */
      approved_at: string;
      /** Approved Revision */
      approved_revision: number;
      /** Calendar Version */
      calendar_version: string;
      /**
       * Decision Cutoff Utc
       * Format: date-time
       */
      decision_cutoff_utc: string;
      /**
       * Eligible Open At
       * Format: date-time
       */
      eligible_open_at: string;
      /**
       * Execution Policy Id
       * @constant
       */
      execution_policy_id: "us_eod_next_open_v1";
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Orders */
      orders: components["schemas"]["PaperOrderV1"][];
      /**
       * Portfolio Id
       * Format: uuid
       */
      portfolio_id: string;
      /** Reason */
      reason: string | null;
      /**
       * Recommendation Id
       * Format: uuid
       */
      recommendation_id: string;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        "pending" | "partially_filled" | "filled" | "cancelled" | "rejected";
      /** Terminal */
      terminal: boolean;
    };
    /** PaperOrderV1 */
    PaperOrderV1: {
      /** Asset Id */
      asset_id: string;
      /** Cancelled Or Skipped Quantity */
      cancelled_or_skipped_quantity: string;
      /**
       * Earliest Fill Session
       * Format: date
       */
      earliest_fill_session: string;
      /** Filled Quantity */
      filled_quantity: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Pending Quantity */
      pending_quantity: string;
      /** Reason */
      reason: string | null;
      /** Requested Quantity */
      requested_quantity: string;
      /**
       * Side
       * @enum {string}
       */
      side: "BUY" | "SELL";
      /**
       * Status
       * @enum {string}
       */
      status:
        "pending" | "partially_filled" | "filled" | "cancelled" | "rejected";
      /** Terminal */
      terminal: boolean;
    };
    /** PaperPortfolioV1 */
    PaperPortfolioV1: {
      /**
       * Benchmark Symbol
       * @default SPY
       * @constant
       */
      benchmark_symbol: "SPY";
      /** Cash Usd */
      cash_usd: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Currency
       * @default USD
       * @constant
       */
      currency: "USD";
      /**
       * Execution Policy Id
       * @default us_eod_next_open_v1
       * @constant
       */
      execution_policy_id: "us_eod_next_open_v1";
      /** Holdings */
      holdings: components["schemas"]["PortfolioHoldingV1"][];
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Last Sequence */
      last_sequence: number;
      /** Name */
      name: string;
      /** Opening Cash Usd */
      opening_cash_usd: string;
      /** Opening Snapshot Id */
      opening_snapshot_id: string | null;
      /**
       * Paper Only
       * @default true
       * @constant
       */
      paper_only: true;
      /** Reconciliation Failed */
      reconciliation_failed: boolean;
      /** Revision */
      revision: number;
      risk_policy: components["schemas"]["PortfolioConfig"];
      /**
       * State
       * @enum {string}
       */
      state: "active" | "paused" | "closed";
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
      /** Total Value Usd */
      total_value_usd: string | null;
      valuation: components["schemas"]["PortfolioValuationV1"];
      /** Valuation As Of Session */
      valuation_as_of_session: string | null;
      /**
       * Valuation Mode
       * @enum {string}
       */
      valuation_mode: "synthetic_fixture" | "research_market_data";
    };
    /** PeriodMetrics */
    PeriodMetrics: {
      /** Daily Nav Observations */
      daily_nav_observations: number;
      metrics: components["schemas"]["ExperimentMetrics"];
      /** Return Observations */
      return_observations: number;
    };
    /** PortfolioConfig */
    PortfolioConfig: {
      /** Max Position Weight */
      max_position_weight: string;
      /** Max Positions */
      max_positions: number;
      /** Max Sector Weight */
      max_sector_weight: string;
      /** Min Cash Weight */
      min_cash_weight: string;
      /** Min Trade Usd */
      min_trade_usd: string;
      /** Rebalance Band Absolute Weight */
      rebalance_band_absolute_weight: string;
      /**
       * Weighting
       * @constant
       */
      weighting: "inverse_volatility";
    };
    /** PortfolioCreateRequest */
    PortfolioCreateRequest: {
      /**
       * Mode
       * @default synthetic_fixture
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /** Name */
      name: string;
      /**
       * Opening Cash Usd
       * @default 1000.00
       */
      opening_cash_usd: string;
      /**
       * Snapshot Id
       * @default null
       */
      snapshot_id: string | null;
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** PortfolioFillV1 */
    PortfolioFillV1: {
      /** Commission Usd */
      commission_usd: string;
      /** Executed Price Usd */
      executed_price_usd: string;
      /**
       * Execution Session
       * Format: date
       */
      execution_session: string;
      /** Gross Usd */
      gross_usd: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Order Id
       * Format: uuid
       */
      order_id: string;
      /** Quantity */
      quantity: string;
      /** Raw Price Usd */
      raw_price_usd: string;
      /** Realized Pnl Usd */
      realized_pnl_usd: string;
      /** Removed Basis Usd */
      removed_basis_usd: string;
      /** Slippage Usd */
      slippage_usd: string;
    };
    /** PortfolioHoldingV1 */
    PortfolioHoldingV1: {
      /** Asset Id */
      asset_id: string;
      /** Mark Price Usd */
      mark_price_usd: string | null;
      /** Market Value Usd */
      market_value_usd: string | null;
      /** Price As Of Session */
      price_as_of_session: string | null;
      /** Quantity */
      quantity: string;
      /** Reason */
      reason: string | null;
      /** Sector */
      sector: string;
      /** Total Basis Usd */
      total_basis_usd: string;
      /** Weight */
      weight: string | null;
    };
    /** PortfolioPositionChangeV1 */
    PortfolioPositionChangeV1: {
      /** Asset Id */
      asset_id: string;
      /** Quantity Delta */
      quantity_delta: string;
      /** Total Basis Delta Usd */
      total_basis_delta_usd: string;
    };
    /** PortfolioState */
    PortfolioState: {
      /**
       * Applied Actions
       * @default []
       */
      applied_actions: components["schemas"]["AppliedAction"][];
      /** Cash Usd */
      cash_usd: string;
      /**
       * Entitlements
       * @default []
       */
      entitlements: components["schemas"]["DividendEntitlement"][];
      /** Positions */
      positions: components["schemas"]["Position"][];
    };
    /** PortfolioTransactionPageV1 */
    PortfolioTransactionPageV1: {
      /** Items */
      items: components["schemas"]["PortfolioTransactionV1"][];
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /** Next Cursor */
      next_cursor: string | null;
      /**
       * Paper Only
       * @default true
       * @constant
       */
      paper_only: true;
      /**
       * Portfolio Id
       * Format: uuid
       */
      portfolio_id: string;
      /**
       * Warnings
       * @default []
       */
      warnings: string[];
    };
    /** PortfolioTransactionV1 */
    PortfolioTransactionV1: {
      /** Cash Delta Usd */
      cash_delta_usd: string;
      /** Correction Target Id */
      correction_target_id: string | null;
      /**
       * Effective At
       * Format: date-time
       */
      effective_at: string;
      /** Event Key */
      event_key: string;
      fill: components["schemas"]["PortfolioFillV1"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Kind
       * @enum {string}
       */
      kind:
        | "opening_funding"
        | "fill"
        | "order_closed"
        | "split"
        | "dividend"
        | "entitlement"
        | "correction"
        | "strategy_binding"
        | "batch_approval"
        | "batch_cancel";
      /** Portfolio Revision */
      portfolio_revision: number;
      /** Position Changes */
      position_changes: components["schemas"]["PortfolioPositionChangeV1"][];
      /**
       * Recorded At
       * Format: date-time
       */
      recorded_at: string;
      /** Sequence */
      sequence: number;
      /** Snapshot Id */
      snapshot_id: string | null;
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** PortfolioValuationV1 */
    PortfolioValuationV1: {
      /** As Of Session */
      as_of_session: string | null;
      /** Cash Weight */
      cash_weight: string | null;
      /**
       * Checked At
       * Format: date-time
       */
      checked_at: string;
      /** Missing Assets */
      missing_assets: string[];
      /** Reason */
      reason: string | null;
      /** Snapshot Id */
      snapshot_id: string | null;
      /** Snapshot Sha256 */
      snapshot_sha256: string | null;
      /**
       * Status
       * @enum {string}
       */
      status: "available" | "stale" | "unavailable";
      /** Total Value Usd */
      total_value_usd: string | null;
      /** Warnings */
      warnings: string[];
    };
    /** Position */
    Position: {
      /** Asset Id */
      asset_id: string;
      /** Quantity */
      quantity: string;
      /** Sector */
      sector: string;
      /** Total Basis Usd */
      total_basis_usd: string;
    };
    /** RNGMetadata */
    RNGMetadata: {
      /**
       * Generator
       * @constant
       */
      generator: "PCG64";
      initial_state: components["schemas"]["ArtifactReference"] | null;
      /** Numpy Version */
      numpy_version: string;
      /**
       * Sampling Version
       * @constant
       */
      sampling_version: "noncircular_c_order_v1";
    };
    /** ReadinessCheck */
    ReadinessCheck: {
      /** Reason */
      reason: string | null;
      /**
       * Status
       * @enum {string}
       */
      status: "ready" | "failed" | "unchecked";
    };
    /** RebalanceConfig */
    RebalanceConfig: {
      /**
       * Frequency
       * @constant
       */
      frequency: "monthly";
    };
    /** RecommendationAccepted */
    RecommendationAccepted: {
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      /**
       * Recommendation Id
       * Format: uuid
       */
      recommendation_id: string;
    };
    /**
     * RecommendationDetailV1
     * @description Original content plus separately changing disposition and forecast job state.
     */
    RecommendationDetailV1: {
      /** Actions */
      actions: components["schemas"]["RecommendedAction"][];
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /** Calendar Sha256 */
      calendar_sha256: string;
      /** Candidates */
      candidates: components["schemas"]["CandidateEvidence"][];
      /** Cash Target Weight */
      cash_target_weight: string;
      /**
       * Clock Mode
       * @enum {string}
       */
      clock_mode: "synthetic_replay" | "current_paper";
      /**
       * Computed At
       * Format: date-time
       */
      computed_at: string;
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Current Portfolio Revision */
      current_portfolio_revision: number;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /**
       * Decision Cutoff Utc
       * Format: date-time
       */
      decision_cutoff_utc: string;
      /** Engine Version */
      engine_version: string;
      /** Estimated Total Trade Cost Usd */
      estimated_total_trade_cost_usd: string;
      forecast: components["schemas"]["ForecastV1"] | null;
      /**
       * Forecast Id
       * Format: uuid
       */
      forecast_id: string;
      /** Forecast Inputs Canonical Json */
      forecast_inputs_canonical_json: string;
      forecast_job: components["schemas"]["JobV1"];
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["RecommendationRequest"];
      /** Inputs Canonical Json */
      inputs_canonical_json: string;
      /** Is Current */
      is_current: boolean;
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      /**
       * Portfolio Id
       * Format: uuid
       */
      portfolio_id: string;
      /** Portfolio Revision */
      portfolio_revision: number;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /** Stale Reasons */
      stale_reasons: string[];
      /**
       * Status
       * @enum {string}
       */
      status: "ready" | "applied" | "dismissed" | "expired";
      strategy_config: components["schemas"]["StrategyConfigV1"];
      strategy_evidence: components["schemas"]["StrategyEvaluationResultV1"];
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
      /**
       * Summary Action
       * @enum {string}
       */
      summary_action:
        "BUY" | "SELL" | "HOLD" | "REBALANCE" | "ALLOCATE_TO_CASH";
      /** Target Weights */
      target_weights: components["schemas"]["TargetWeight"][];
    };
    /** RecommendationPageV1 */
    RecommendationPageV1: {
      /** Items */
      items: components["schemas"]["RecommendationSummaryV1"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /** RecommendationRequest */
    RecommendationRequest: {
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /**
       * Clock Mode
       * @enum {string}
       */
      clock_mode: "synthetic_replay" | "current_paper";
      /**
       * Seed
       * @default 42
       */
      seed: number;
      /**
       * Snapshot Id
       * @default null
       */
      snapshot_id: string | null;
    };
    /** RecommendationSummaryV1 */
    RecommendationSummaryV1: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /** Disposition */
      disposition: ("ready" | "applied" | "dismissed" | "expired") | null;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["RecommendationRequest"];
      /** Inputs Canonical Json */
      inputs_canonical_json: string;
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      /**
       * Portfolio Id
       * Format: uuid
       */
      portfolio_id: string;
      /** Portfolio Revision */
      portfolio_revision: number;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** RecommendationV1 */
    RecommendationV1: {
      /** Actions */
      actions: components["schemas"]["RecommendedAction"][];
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /** Candidates */
      candidates: components["schemas"]["CandidateEvidence"][];
      /** Cash Target Weight */
      cash_target_weight: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Data Status
       * @enum {string}
       */
      data_status: "synthetic_fixture" | "research_market_data";
      /**
       * Decision Cutoff Utc
       * Format: date-time
       */
      decision_cutoff_utc: string;
      /** Engine Version */
      engine_version: string;
      /** Estimated Total Trade Cost Usd */
      estimated_total_trade_cost_usd: string;
      /**
       * Forecast Id
       * Format: uuid
       */
      forecast_id: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Portfolio Id
       * Format: uuid
       */
      portfolio_id: string;
      /** Portfolio Revision */
      portfolio_revision: number;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ready" | "applied" | "dismissed" | "expired";
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
      /**
       * Summary Action
       * @enum {string}
       */
      summary_action:
        "BUY" | "SELL" | "HOLD" | "REBALANCE" | "ALLOCATE_TO_CASH";
      /** Target Weights */
      target_weights: components["schemas"]["TargetWeight"][];
    };
    /** RecommendedAction */
    RecommendedAction: {
      /** Asset Id */
      asset_id: string;
      /** Current Weight */
      current_weight: string;
      /** Estimated Notional Usd */
      estimated_notional_usd: string;
      /** Estimated Quantity */
      estimated_quantity: string;
      evidence: components["schemas"]["ActionEvidence"];
      /** Explanation */
      explanation: string;
      /**
       * Label
       * @enum {string}
       */
      label: "INCREASE" | "REDUCE" | "HOLD";
      /** Reason Codes */
      reason_codes: string[];
      /**
       * Side
       * @enum {string}
       */
      side: "BUY" | "SELL" | "HOLD";
      /** Target Weight */
      target_weight: string;
    };
    /** RefreshPayload */
    RefreshPayload: {
      /** Expected Manifest Hash */
      expected_manifest_hash?: string | null;
      /** Research Config */
      research_config?:
        | components["schemas"]["ResearchConfig"]
        | components["schemas"]["TiingoResearchConfigV1"]
        | null;
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      /**
       * Source Mode
       * @enum {string}
       */
      source_mode: "synthetic_fixture" | "research_market_data";
    };
    /** ResearchConfig */
    ResearchConfig: {
      /**
       * Adapter Version
       * @constant
       */
      adapter_version: "yfinance_1.7.0_normalization_1";
      /** Assets */
      assets: components["schemas"]["AssetV1"][];
      calendar: components["schemas"]["Calendar"];
      context: components["schemas"]["AssetContext"];
      /**
       * Directory Kind
       * @enum {string}
       */
      directory_kind: "nasdaqlisted" | "otherlisted";
      /** Directory Reference */
      directory_reference: string;
      /** Exchange Codes */
      exchange_codes: string[];
      /**
       * First Session
       * Format: date
       */
      first_session: string;
      /**
       * Last Session
       * Format: date
       */
      last_session: string;
      /** Rights Reference */
      rights_reference: string;
      /** Rights Verified Local Use */
      rights_verified_local_use: boolean;
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      /** Selection Rule Reference */
      selection_rule_reference: string;
    };
    /** RiskReport */
    RiskReport: {
      /** Capped Positions */
      capped_positions: string[];
      /** Cash Floor */
      cash_floor: string;
      /** Cash Weight */
      cash_weight: string;
      /** Compliant */
      compliant: boolean;
      /** Invested Weight */
      invested_weight: string;
      /** Max Position Weight */
      max_position_weight: string;
      /** Max Sector Weight */
      max_sector_weight: string;
      /** Position Count */
      position_count: number;
      /** Position Limit */
      position_limit: string;
      /** Sector Limit */
      sector_limit: string;
      /** Sectors */
      sectors: components["schemas"]["SectorRisk"][];
      /** Unmet Investable Weight */
      unmet_investable_weight: string;
      /** Violations */
      violations: string[];
    };
    /** ScoreEvidence */
    ScoreEvidence: {
      /** Momentum Long Contribution */
      momentum_long_contribution: number;
      /** Momentum Long Z */
      momentum_long_z: number;
      /** Momentum Short Contribution */
      momentum_short_contribution: number;
      /** Momentum Short Z */
      momentum_short_z: number;
      /** Score */
      score: number;
      /** Volatility Contribution */
      volatility_contribution: number;
      /** Volatility Z */
      volatility_z: number;
    };
    /** ScoreWeights */
    ScoreWeights: {
      /** Momentum Long */
      momentum_long: number;
      /** Momentum Short */
      momentum_short: number;
      /** Volatility Penalty */
      volatility_penalty: number;
    };
    /** Sector */
    Sector: {
      /** Asset Id */
      asset_id: string;
      /**
       * Available At
       * Format: date-time
       */
      available_at: string;
      /**
       * Effective From
       * Format: date
       */
      effective_from: string;
      /** Effective To Exclusive */
      effective_to_exclusive: string | null;
      /**
       * Ingested At
       * Format: date-time
       */
      ingested_at: string;
      /** Provider */
      provider: string;
      /** Sector */
      sector: string;
    };
    /** SectorRisk */
    SectorRisk: {
      /** At Cap */
      at_cap: boolean;
      /** Sector */
      sector: string;
      /** Weight */
      weight: string;
    };
    /** Session */
    Session: {
      /**
       * Close At
       * Format: date-time
       */
      close_at: string;
      /**
       * Open At
       * Format: date-time
       */
      open_at: string;
      /**
       * Session Date
       * Format: date
       */
      session_date: string;
    };
    /** SignalConfig */
    SignalConfig: {
      /**
       * @description discriminator enum property added by openapi-typescript
       * @enum {string}
       */
      kind: "risk_adjusted_momentum";
      /** Momentum Long Sessions */
      momentum_long_sessions: number;
      /** Momentum Short Sessions */
      momentum_short_sessions: number;
      /** Require Positive Trend */
      require_positive_trend: boolean;
      /** Trend Sma Sessions */
      trend_sma_sessions: number;
      /** Volatility Sessions */
      volatility_sessions: number;
      z_score_weights: components["schemas"]["ScoreWeights"];
    };
    /** SnapshotArtifact */
    SnapshotArtifact: {
      /**
       * Format
       * @enum {string}
       */
      format: "parquet" | "json";
      /** Path */
      path: string;
      /**
       * Role
       * @enum {string}
       */
      role:
        | "bars"
        | "assets"
        | "actions"
        | "universe"
        | "calendar"
        | "provenance"
        | "coverage";
      /** Row Count */
      row_count: number | null;
      /** Schema Version */
      schema_version: number;
      /** Sha256 */
      sha256: string;
      /** Size Bytes */
      size_bytes: number;
    };
    /** SnapshotCoverage */
    SnapshotCoverage: {
      /** Asset Ids */
      asset_ids: string[];
      /** First Session */
      first_session: string | null;
      /** Last Session */
      last_session: string | null;
      /** Latest Completed Session */
      latest_completed_session: string | null;
      /**
       * Membership Basis
       * @enum {string}
       */
      membership_basis: "point_in_time" | "current_only" | "synthetic";
      /** Missing Sessions */
      missing_sessions: components["schemas"]["MissingSession"][];
    };
    /** SnapshotManifestV1 */
    SnapshotManifestV1: {
      /** Artifacts */
      artifacts: components["schemas"]["SnapshotArtifact"][];
      calendar: components["schemas"]["CalendarReference"];
      coverage: components["schemas"]["SnapshotCoverage"];
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      price_basis: components["schemas"]["SnapshotPriceBasis"];
      /**
       * Quality
       * @enum {string}
       */
      quality: "usable" | "usable_with_warnings" | "blocked";
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      source: components["schemas"]["SnapshotSource"];
      /** Warnings */
      warnings: string[];
    };
    /** SnapshotPriceBasis */
    SnapshotPriceBasis: {
      /** Adjusted Close */
      adjusted_close: string;
      /** Corporate Action Policy */
      corporate_action_policy: string;
      /**
       * Currency
       * @constant
       */
      currency: "USD";
      /**
       * Ohlc
       * @enum {string}
       */
      ohlc: "raw_as_traded" | "provider_unverified";
      /** Volume */
      volume: string;
    };
    /** SnapshotSource */
    SnapshotSource: {
      /** Adapter Version */
      adapter_version: string;
      /** Capabilities Sha256 */
      capabilities_sha256: string;
      /** Normalization Version */
      normalization_version: string;
      /** Provider */
      provider: string;
      /** Rights Reference */
      rights_reference: string | null;
      /**
       * Rights Status
       * @enum {string}
       */
      rights_status: "synthetic_owned" | "verified_local_use" | "unverified";
    };
    /** SnapshotV1 */
    SnapshotV1: {
      /** Asset Count */
      asset_count: number;
      coverage: components["schemas"]["SnapshotCoverage"];
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Latest Completed Session */
      latest_completed_session: string | null;
      /** Manifest Sha256 */
      manifest_sha256: string;
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /** Provider */
      provider: string;
      /**
       * Published At
       * Format: date-time
       */
      published_at: string;
      /**
       * Quality
       * @enum {string}
       */
      quality: "usable" | "usable_with_warnings" | "blocked";
      /** Warnings */
      warnings: string[];
    };
    /** StrategyConfigV1 */
    StrategyConfigV1: {
      /** Display Name */
      display_name: string;
      execution_policy: components["schemas"]["backend__domain__strategy__ExecutionPolicy"];
      portfolio: components["schemas"]["PortfolioConfig"];
      rebalance: components["schemas"]["RebalanceConfig"];
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      /** Signals */
      signals:
        | components["schemas"]["SignalConfig"]
        | components["schemas"]["MeanReversionSignalConfig"]
        | components["schemas"]["LowVolatilitySignalConfig"];
      universe: components["schemas"]["UniverseConfig"];
    };
    /** StrategyCreateRequest */
    StrategyCreateRequest: {
      config: components["schemas"]["StrategyConfigV1"];
      /** Name */
      name: string;
    };
    /** StrategyEvaluationAccepted */
    StrategyEvaluationAccepted: {
      /**
       * Evaluation Id
       * Format: uuid
       */
      evaluation_id: string;
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
    };
    /** StrategyEvaluationRequest */
    StrategyEvaluationRequest: {
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /**
       * Snapshot Id
       * Format: uuid
       */
      snapshot_id: string;
      /**
       * Strategy Version Id
       * Format: uuid
       */
      strategy_version_id: string;
    };
    /** StrategyEvaluationResultV1 */
    StrategyEvaluationResultV1: {
      /** Allocation Exclusions */
      allocation_exclusions: components["schemas"]["AllocationExclusion"][];
      /** Allocation Reasons */
      allocation_reasons: string[];
      /**
       * As Of Session
       * Format: date
       */
      as_of_session: string;
      /** Candidates */
      candidates: components["schemas"]["EvaluationCandidateV1"][];
      /** Cash Target Weight */
      cash_target_weight: string;
      constraint_evidence: components["schemas"]["RiskReport"];
      /** Data Diagnostics */
      data_diagnostics: components["schemas"]["DataDiagnosticEvidence"][];
      /**
       * Decision Cutoff Utc
       * Format: date-time
       */
      decision_cutoff_utc: string;
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      reproducibility: components["schemas"]["EvaluationReproducibilityV1"];
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      schema_version: 1;
      /** Selected Ids */
      selected_ids: string[];
      /** Target Weights */
      target_weights: components["schemas"]["AllocationTarget"][];
      /** Warnings */
      warnings: string[];
    };
    /** StrategyEvaluationV1 */
    StrategyEvaluationV1: {
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /** Engine Version */
      engine_version: string;
      error: components["schemas"]["ErrorDetail"] | null;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      inputs: components["schemas"]["StrategyEvaluationRequest"];
      /**
       * Job Id
       * Format: uuid
       */
      job_id: string;
      /**
       * Mode
       * @enum {string}
       */
      mode: "synthetic_fixture" | "research_market_data";
      /** Provider */
      provider: string;
      result: components["schemas"]["StrategyEvaluationResultV1"] | null;
      /** Result Sha256 */
      result_sha256: string | null;
      /** Snapshot Sha256 */
      snapshot_sha256: string;
      /**
       * Status
       * @enum {string}
       */
      status:
        | "queued"
        | "running"
        | "cancel_requested"
        | "completed"
        | "failed"
        | "cancelled";
      strategy_config: components["schemas"]["StrategyConfigV1"];
    };
    /** StrategyV1 */
    StrategyV1: {
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Is Template */
      is_template: boolean;
      /** Name */
      name: string;
      published_version: components["schemas"]["StrategyVersionV1"];
      /** Template Key */
      template_key: string | null;
    };
    /** StrategyVersionV1 */
    StrategyVersionV1: {
      config: components["schemas"]["StrategyConfigV1"];
      /** Config Sha256 */
      config_sha256: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Published At
       * Format: date-time
       */
      published_at: string;
      /**
       * Status
       * @constant
       */
      status: "published";
      /**
       * Strategy Id
       * Format: uuid
       */
      strategy_id: string;
      /** Version */
      version: number;
    };
    /** TargetWeight */
    TargetWeight: {
      /** Asset Id */
      asset_id: string;
      /** Reason Codes */
      reason_codes: string[];
      /** Weight */
      weight: string;
    };
    /** TiingoResearchConfigV1 */
    TiingoResearchConfigV1: {
      /** As Of Session */
      as_of_session?: string | null;
      /**
       * History Sessions
       * @default 400
       */
      history_sessions: number;
      /**
       * Max Assets
       * @default 20
       */
      max_assets: number;
      /**
       * Provider
       * @constant
       */
      provider: "tiingo_eod";
      /**
       * Rights Reference
       * @default https://www.tiingo.com/documentation/
       * @constant
       */
      rights_reference: "https://www.tiingo.com/documentation/";
      /** Rights Verified Local Use */
      rights_verified_local_use: boolean;
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
    };
    /** UniverseConfig */
    UniverseConfig: {
      /**
       * Kind
       * @constant
       */
      kind: "liquid_us_equities";
      /** Min History Sessions */
      min_history_sessions: number;
      /** Min Median Dollar Volume Usd */
      min_median_dollar_volume_usd: string;
      /** Min Price Usd */
      min_price_usd: string;
    };
    /** ValidationError */
    ValidationError: {
      /** Context */
      ctx?: Record<string, never>;
      /** Input */
      input?: unknown;
      /** Location */
      loc: (string | number)[];
      /** Message */
      msg: string;
      /** Error Type */
      type: string;
    };
    /** WeightValue */
    WeightValue: {
      /** Unavailable Reason */
      unavailable_reason: string | null;
      /** Value */
      value: string | null;
    };
    /** WorkspaceV1 */
    WorkspaceV1: {
      /** Default Benchmark */
      default_benchmark: string;
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Locale */
      locale: string;
      /**
       * Paper Only
       * @default true
       * @constant
       */
      paper_only: true;
      /** Preferences */
      preferences: {
        [key: string]: components["schemas"]["JsonValue"];
      };
    };
    /** ExecutionPolicy */
    backend__domain__strategy__ExecutionPolicy: {
      /**
       * Id
       * @constant
       */
      id: "us_eod_next_open_v1";
    };
    /** ExecutionPolicy */
    backend__portfolio__execution__ExecutionPolicy: {
      /**
       * Commission Usd
       * @default 0.00
       */
      commission_usd: string;
      /**
       * Id
       * @default us_eod_next_open_v1
       * @constant
       */
      id: "us_eod_next_open_v1";
      /**
       * Slippage Fraction
       * @default 0.001
       */
      slippage_fraction: string;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  assets_api_v1_data_assets_get: {
    parameters: {
      query: {
        mode: "synthetic_fixture" | "research_market_data";
        snapshot_id: string;
        query?: string;
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AssetPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  health_api_v1_data_health_get: {
    parameters: {
      query: {
        mode: "synthetic_fixture" | "research_market_data";
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DataHealthV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  refresh_api_v1_data_refresh_post: {
    parameters: {
      query?: never;
      header: {
        "Idempotency-Key": string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["RefreshPayload"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["JobV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  snapshots_api_v1_data_snapshots_get: {
    parameters: {
      query: {
        mode: "synthetic_fixture" | "research_market_data";
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_SnapshotV1_"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  list_experiments_api_v1_experiments_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ExperimentPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  create_api_v1_experiments_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ExperimentRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ExperimentAccepted"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  read_api_v1_experiments__experiment_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        experiment_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ExperimentDetailV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  series_api_v1_experiments__experiment_id__series_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
        start_session?: string | null;
        end_session_exclusive?: string | null;
      };
      header?: never;
      path: {
        experiment_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ExperimentSeriesPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  trades_api_v1_experiments__experiment_id__trades_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
        start_session?: string | null;
        end_session_exclusive?: string | null;
      };
      header?: never;
      path: {
        experiment_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ExperimentTradesPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  read_api_v1_forecasts__forecast_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        forecast_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ForecastV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  health_api_v1_health_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthV1"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HealthV1"];
        };
      };
    };
  };
  get_job_api_v1_jobs__job_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        job_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["JobV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["HTTPValidationError"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  cancel_job_api_v1_jobs__job_id__cancel_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        job_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["JobCancelRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["JobV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  accounts_api_v1_portfolios_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
        mode?: ("synthetic_fixture" | "research_market_data") | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_PaperPortfolioV1_"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  create_api_v1_portfolios_post: {
    parameters: {
      query?: never;
      header: {
        "Idempotency-Key": string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["PortfolioCreateRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PaperPortfolioV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  detail_api_v1_portfolios__portfolio_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        portfolio_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PaperPortfolioV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  list_recommendations_api_v1_portfolios__portfolio_id__recommendations_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path: {
        portfolio_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RecommendationPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  create_api_v1_portfolios__portfolio_id__recommendations_post: {
    parameters: {
      query?: never;
      header?: {
        "Idempotency-Key"?: string | null;
      };
      path: {
        portfolio_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["RecommendationRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RecommendationAccepted"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  transactions_api_v1_portfolios__portfolio_id__transactions_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path: {
        portfolio_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PortfolioTransactionPageV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  read_api_v1_recommendations__recommendation_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        recommendation_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RecommendationDetailV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  strategies_api_v1_strategies_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_StrategyV1_"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  create_api_v1_strategies_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["StrategyCreateRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StrategyV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  detail_api_v1_strategies__strategy_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        strategy_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StrategyV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  versions_api_v1_strategies__strategy_id__versions_get: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string | null;
      };
      header?: never;
      path: {
        strategy_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Page_StrategyVersionV1_"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  publish_api_v1_strategies__strategy_id__versions_post: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        strategy_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["StrategyConfigV1"];
      };
    };
    responses: {
      /** @description Successful Response */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StrategyVersionV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  create_api_v1_strategy_evaluations_post: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["StrategyEvaluationRequest"];
      };
    };
    responses: {
      /** @description Successful Response */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StrategyEvaluationAccepted"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  read_api_v1_strategy_evaluations__evaluation_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        evaluation_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StrategyEvaluationV1"];
        };
      };
      /** @description Not Found */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Conflict */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Unprocessable Content */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  workspace_api_v1_workspace_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["WorkspaceV1"];
        };
      };
      /** @description Service Unavailable */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  liveness_livez_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Liveness"];
        };
      };
    };
  };
}

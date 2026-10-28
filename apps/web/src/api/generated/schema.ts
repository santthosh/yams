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
    post?: never;
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
      features: components["schemas"]["FeatureValues"] | null;
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
      scoring: components["schemas"]["ScoreEvidence"] | null;
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
    /** ExecutionPolicy */
    ExecutionPolicy: {
      /**
       * Id
       * @constant
       */
      id: "us_eod_next_open_v1";
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
    /** MetricValue */
    MetricValue: {
      /** Unavailable Reason */
      unavailable_reason: string | null;
      /** Value */
      value: number | null;
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
       * Kind
       * @constant
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
      execution_policy: components["schemas"]["ExecutionPolicy"];
      portfolio: components["schemas"]["PortfolioConfig"];
      rebalance: components["schemas"]["RebalanceConfig"];
      /**
       * Schema Version
       * @constant
       */
      schema_version: 1;
      signals: components["schemas"]["SignalConfig"];
      universe: components["schemas"]["UniverseConfig"];
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

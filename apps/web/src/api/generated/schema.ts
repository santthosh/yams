export interface paths {
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
    /** ScoreWeights */
    ScoreWeights: {
      /** Momentum Long */
      momentum_long: number;
      /** Momentum Short */
      momentum_short: number;
      /** Volatility Penalty */
      volatility_penalty: number;
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
    /** TargetWeight */
    TargetWeight: {
      /** Asset Id */
      asset_id: string;
      /** Reason Codes */
      reason_codes: string[];
      /** Weight */
      weight: string;
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

--
-- PostgreSQL database dump
--


-- Dumped from database version 17.7
-- Dumped by pg_dump version 17.7

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--



--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Extensions (manuell vorangestellt: pg_dump --schema=public laesst globale Extensions weg)
--

CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;



SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: backtest_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_configs (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    symbol character varying(20) DEFAULT 'BTCUSDT'::character varying NOT NULL,
    exchange character varying(50) DEFAULT 'binance'::character varying NOT NULL,
    timeframe character varying(10) DEFAULT '4h'::character varying NOT NULL,
    start character varying(20) NOT NULL,
    "end" character varying(20) NOT NULL,
    ohlc_start character varying(20) NOT NULL,
    ohlc_end character varying(20) NOT NULL,
    size double precision DEFAULT 100 NOT NULL,
    size_type character varying(20) DEFAULT 'value'::character varying NOT NULL,
    init_cash double precision DEFAULT 100 NOT NULL,
    fees double precision DEFAULT 0.001 NOT NULL,
    tp_stop double precision,
    sl_stop double precision,
    tsl_th double precision,
    tsl_stop double precision,
    td_stop integer,
    delta_format character varying(20) DEFAULT 'percent'::character varying NOT NULL,
    time_delta_format character varying(20) DEFAULT 'rows'::character varying NOT NULL,
    is_default smallint DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone
);


--
-- Name: backtest_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_configs_id_seq OWNED BY public.backtest_configs.id;


--
-- Name: backtest_result_equity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_equity (
    id integer NOT NULL,
    result_id integer NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    value double precision
);


--
-- Name: backtest_equity_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_equity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_equity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_equity_id_seq OWNED BY public.backtest_result_equity.id;


--
-- Name: backtest_result_indicators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_indicators (
    id integer NOT NULL,
    result_id integer NOT NULL,
    indicator_name character varying(100) NOT NULL,
    indicator_output character varying(100) NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    value double precision
);


--
-- Name: backtest_indicators_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_indicators_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_indicators_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_indicators_id_seq OWNED BY public.backtest_result_indicators.id;


--
-- Name: backtest_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_jobs (
    id integer NOT NULL,
    run_id integer NOT NULL,
    result_id integer NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    error_message text,
    rq_job_id character varying(64),
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: backtest_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_jobs_id_seq OWNED BY public.backtest_jobs.id;


--
-- Name: backtest_result_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_orders (
    id integer NOT NULL,
    result_id integer NOT NULL,
    order_id integer NOT NULL,
    signal_index timestamp without time zone,
    creation_index timestamp without time zone,
    fill_index timestamp without time zone,
    size double precision NOT NULL,
    price double precision NOT NULL,
    fees double precision,
    side character varying(10) NOT NULL,
    type character varying(50),
    stop_type character varying(50)
);


--
-- Name: backtest_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_orders_id_seq OWNED BY public.backtest_result_orders.id;


--
-- Name: backtest_result_params; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_params (
    id integer NOT NULL,
    result_id integer NOT NULL,
    param_name character varying(100) NOT NULL,
    param_value double precision
);


--
-- Name: backtest_params_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_params_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_params_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_params_id_seq OWNED BY public.backtest_result_params.id;


--
-- Name: backtest_result_positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_positions (
    id integer NOT NULL,
    result_id integer NOT NULL,
    position_id integer NOT NULL,
    direction character varying(10) DEFAULT 'Long'::character varying NOT NULL,
    status character varying(10) DEFAULT 'Closed'::character varying NOT NULL,
    size double precision NOT NULL,
    entry_order_id integer,
    entry_index timestamp without time zone NOT NULL,
    avg_entry_price double precision NOT NULL,
    entry_fees double precision,
    exit_order_id integer,
    exit_index timestamp without time zone,
    avg_exit_price double precision,
    exit_fees double precision,
    pnl double precision,
    return_pct double precision
);


--
-- Name: backtest_positions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_positions_id_seq OWNED BY public.backtest_result_positions.id;


--
-- Name: backtest_result_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_result_trades (
    id integer NOT NULL,
    result_id integer NOT NULL,
    exit_trade_id integer NOT NULL,
    position_id integer,
    direction character varying(10) DEFAULT 'Long'::character varying NOT NULL,
    status character varying(10) DEFAULT 'Closed'::character varying NOT NULL,
    size double precision NOT NULL,
    entry_order_id integer,
    entry_index timestamp without time zone NOT NULL,
    avg_entry_price double precision NOT NULL,
    entry_fees double precision,
    exit_order_id integer,
    exit_index timestamp without time zone,
    avg_exit_price double precision,
    exit_fees double precision,
    pnl double precision,
    return_pct double precision
);


--
-- Name: backtest_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_results (
    id integer NOT NULL,
    run_id integer NOT NULL,
    params_hash character(32) NOT NULL,
    actual_params_json jsonb NOT NULL,
    start_index timestamp without time zone,
    end_index timestamp without time zone,
    total_duration character varying(50),
    start_value double precision,
    min_value double precision,
    max_value double precision,
    end_value double precision,
    total_return_pct double precision,
    benchmark_return_pct double precision,
    position_coverage_pct double precision,
    max_gross_exposure_pct double precision,
    max_drawdown_pct double precision,
    max_drawdown_duration character varying(50),
    total_orders integer,
    total_fees_paid double precision,
    total_trades integer,
    win_rate_pct double precision,
    best_trade_pct double precision,
    worst_trade_pct double precision,
    avg_winning_trade_pct double precision,
    avg_losing_trade_pct double precision,
    avg_winning_trade_duration character varying(50),
    avg_losing_trade_duration character varying(50),
    profit_factor double precision,
    expectancy double precision,
    sharpe_ratio double precision,
    calmar_ratio double precision,
    omega_ratio double precision,
    sortino_ratio double precision,
    annualized_return double precision,
    annualized_volatility double precision,
    downside_risk double precision,
    tail_ratio double precision,
    value_at_risk double precision,
    cond_value_at_risk double precision,
    alpha double precision,
    beta double precision,
    information_ratio double precision,
    sqn double precision,
    edge_ratio double precision,
    deflated_sharpe_ratio double precision,
    metrics_level character varying(10) DEFAULT 'partial'::character varying NOT NULL,
    is_favorite smallint DEFAULT 0 NOT NULL,
    resolved_config_json jsonb,
    spec_runner_version character varying(20),
    iteration_id integer,
    is_doc_favorite integer DEFAULT 0 NOT NULL,
    full_config_snapshot_json json
);


--
-- Name: backtest_results_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_results_id_seq OWNED BY public.backtest_results.id;


--
-- Name: backtest_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backtest_runs (
    id integer NOT NULL,
    strategy_family character varying(100) NOT NULL,
    strategy_name character varying(100) NOT NULL,
    symbol character varying(20) NOT NULL,
    exchange character varying(50) NOT NULL,
    timeframe character varying(10) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    backtest_config_json jsonb NOT NULL,
    indicators_config_json jsonb NOT NULL,
    n_combinations integer DEFAULT 0 NOT NULL,
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    error_message text,
    remarks text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    parent_run_id integer,
    parent_result_id integer,
    selection_metric character varying(50),
    spec_runner_version character varying(20),
    testset_run_id integer,
    iteration_id integer,
    backtest_config_id integer,
    indicator_config_id integer
);


--
-- Name: backtest_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_runs_id_seq OWNED BY public.backtest_runs.id;


--
-- Name: backtest_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.backtest_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: backtest_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.backtest_trades_id_seq OWNED BY public.backtest_result_trades.id;


--
-- Name: chart_playground_setups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chart_playground_setups (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone,
    backtest_config_json jsonb NOT NULL,
    indicators_config_json jsonb NOT NULL,
    strategy_config_json jsonb NOT NULL,
    ui_state_json jsonb
);


--
-- Name: chart_playground_setups_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chart_playground_setups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chart_playground_setups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chart_playground_setups_id_seq OWNED BY public.chart_playground_setups.id;


--
-- Name: indicator_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.indicator_configs (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    config_json jsonb NOT NULL,
    is_default smallint DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone,
    strategy_concept_id integer,
    strategy_iteration_id integer
);


--
-- Name: indicator_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.indicator_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: indicator_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.indicator_configs_id_seq OWNED BY public.indicator_configs.id;


--
-- Name: leaderboard_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leaderboard_entries (
    id integer NOT NULL,
    testset_id integer NOT NULL,
    testset_run_id integer,
    strategy_family character varying(100) NOT NULL,
    strategy_name character varying(100) NOT NULL,
    indicator_config_id integer,
    spec_runner_version character varying(20),
    total_return_avg numeric(12,4),
    total_return_sum numeric(12,4),
    max_drawdown_avg numeric(12,4),
    sharpe_avg numeric(12,4),
    configs_total integer NOT NULL,
    configs_passed integer,
    filter_breached boolean,
    testset_snapshot_json jsonb NOT NULL,
    indicator_config_snapshot_json jsonb,
    strategy_snapshot_json jsonb NOT NULL,
    winning_result_ids_json jsonb NOT NULL,
    hint text,
    executive_summary text,
    mini_report text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: leaderboard_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.leaderboard_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: leaderboard_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.leaderboard_entries_id_seq OWNED BY public.leaderboard_entries.id;


--
-- Name: ohlc_download_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ohlc_download_jobs (
    id integer NOT NULL,
    job_type character varying(20) DEFAULT 'download'::character varying NOT NULL,
    exchange character varying(20) DEFAULT 'binance'::character varying NOT NULL,
    timeframe character varying(10) NOT NULL,
    symbols jsonb NOT NULL,
    start_date character varying(50),
    end_date character varying(50),
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    message text,
    rq_job_id character varying(64),
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ohlc_download_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ohlc_download_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ohlc_download_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ohlc_download_jobs_id_seq OWNED BY public.ohlc_download_jobs.id;


--
-- Name: strategy_concepts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_concepts (
    id integer NOT NULL,
    slug character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    category character varying(50),
    description text,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    created_by character varying(120),
    iteration_counter integer DEFAULT 0 NOT NULL,
    CONSTRAINT ck_strategy_concepts_status CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('active'::character varying)::text, ('archived'::character varying)::text])))
);


--
-- Name: strategy_concepts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.strategy_concepts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: strategy_concepts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.strategy_concepts_id_seq OWNED BY public.strategy_concepts.id;


--
-- Name: strategy_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_configs (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    strategy_family character varying(100) NOT NULL,
    strategy_name character varying(100) NOT NULL,
    import_path character varying(500),
    is_default integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone,
    type character varying(20) NOT NULL,
    strategy_config_json jsonb
);


--
-- Name: strategy_configs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.strategy_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: strategy_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.strategy_configs_id_seq OWNED BY public.strategy_configs.id;


--
-- Name: strategy_iterations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.strategy_iterations (
    id integer NOT NULL,
    concept_id integer NOT NULL,
    version integer NOT NULL,
    spec_json jsonb,
    parent_iteration_id integer,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    created_by character varying(120),
    spec_hash character varying(16),
    type character varying(20) NOT NULL,
    import_path character varying(500),
    description text,
    is_favorite boolean DEFAULT false NOT NULL,
    updated_at timestamp without time zone,
    version_name character varying(100),
    is_doc_favorite boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_strategy_iterations_status CHECK (((status)::text = ANY (ARRAY[('draft'::character varying)::text, ('active'::character varying)::text, ('archived'::character varying)::text, ('live'::character varying)::text])))
);


--
-- Name: strategy_iterations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.strategy_iterations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: strategy_iterations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.strategy_iterations_id_seq OWNED BY public.strategy_iterations.id;


--
-- Name: testsets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.testsets (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    backtest_config_ids_json jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by character varying(120)
);


--
-- Name: test_sets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.test_sets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: test_sets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.test_sets_id_seq OWNED BY public.testsets.id;


--
-- Name: testset_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.testset_runs (
    id integer NOT NULL,
    testset_id integer NOT NULL,
    strategy_family character varying(100) NOT NULL,
    strategy_name character varying(100) NOT NULL,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    n_runs_total integer NOT NULL,
    n_runs_completed integer DEFAULT 0 NOT NULL,
    triggered_by character varying(120),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp without time zone,
    created_by character varying(120),
    indicators_config_json jsonb NOT NULL,
    CONSTRAINT ck_testset_runs_status CHECK (((status)::text = ANY (ARRAY[('queued'::character varying)::text, ('running'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text])))
);


--
-- Name: testset_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.testset_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: testset_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.testset_runs_id_seq OWNED BY public.testset_runs.id;


--
-- Name: vault_chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vault_chunks (
    id integer NOT NULL,
    vault_path character varying(1024) NOT NULL,
    chunk_index integer NOT NULL,
    heading_path character varying(1024),
    content text,
    frontmatter_json jsonb,
    mtime timestamp without time zone NOT NULL,
    embedding public.vector(1024),
    indexed_at timestamp without time zone DEFAULT now() NOT NULL,
    file_sha1 character varying(40) DEFAULT ''::character varying NOT NULL
);


--
-- Name: vault_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.vault_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vault_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.vault_chunks_id_seq OWNED BY public.vault_chunks.id;


--
-- Name: vault_reindex_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vault_reindex_runs (
    id integer NOT NULL,
    job_id character varying(255) NOT NULL,
    scope character varying(50) NOT NULL,
    target_path character varying(1024),
    trigger character varying(50) NOT NULL,
    status character varying(50) DEFAULT 'queued'::character varying NOT NULL,
    started_at timestamp without time zone,
    finished_at timestamp without time zone,
    duration_seconds double precision,
    files_scanned integer,
    files_reindexed integer,
    files_deleted integer,
    chunks_written integer,
    error_message text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    files_changed jsonb
);


--
-- Name: vault_reindex_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.vault_reindex_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: vault_reindex_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.vault_reindex_runs_id_seq OWNED BY public.vault_reindex_runs.id;


--
-- Name: backtest_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_configs ALTER COLUMN id SET DEFAULT nextval('public.backtest_configs_id_seq'::regclass);


--
-- Name: backtest_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_jobs ALTER COLUMN id SET DEFAULT nextval('public.backtest_jobs_id_seq'::regclass);


--
-- Name: backtest_result_equity id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_equity ALTER COLUMN id SET DEFAULT nextval('public.backtest_equity_id_seq'::regclass);


--
-- Name: backtest_result_indicators id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_indicators ALTER COLUMN id SET DEFAULT nextval('public.backtest_indicators_id_seq'::regclass);


--
-- Name: backtest_result_orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_orders ALTER COLUMN id SET DEFAULT nextval('public.backtest_orders_id_seq'::regclass);


--
-- Name: backtest_result_params id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_params ALTER COLUMN id SET DEFAULT nextval('public.backtest_params_id_seq'::regclass);


--
-- Name: backtest_result_positions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_positions ALTER COLUMN id SET DEFAULT nextval('public.backtest_positions_id_seq'::regclass);


--
-- Name: backtest_result_trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_trades ALTER COLUMN id SET DEFAULT nextval('public.backtest_trades_id_seq'::regclass);


--
-- Name: backtest_results id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results ALTER COLUMN id SET DEFAULT nextval('public.backtest_results_id_seq'::regclass);


--
-- Name: backtest_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_runs ALTER COLUMN id SET DEFAULT nextval('public.backtest_runs_id_seq'::regclass);


--
-- Name: chart_playground_setups id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_playground_setups ALTER COLUMN id SET DEFAULT nextval('public.chart_playground_setups_id_seq'::regclass);


--
-- Name: indicator_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_configs ALTER COLUMN id SET DEFAULT nextval('public.indicator_configs_id_seq'::regclass);


--
-- Name: leaderboard_entries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leaderboard_entries ALTER COLUMN id SET DEFAULT nextval('public.leaderboard_entries_id_seq'::regclass);


--
-- Name: ohlc_download_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ohlc_download_jobs ALTER COLUMN id SET DEFAULT nextval('public.ohlc_download_jobs_id_seq'::regclass);


--
-- Name: strategy_concepts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_concepts ALTER COLUMN id SET DEFAULT nextval('public.strategy_concepts_id_seq'::regclass);


--
-- Name: strategy_configs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_configs ALTER COLUMN id SET DEFAULT nextval('public.strategy_configs_id_seq'::regclass);


--
-- Name: strategy_iterations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_iterations ALTER COLUMN id SET DEFAULT nextval('public.strategy_iterations_id_seq'::regclass);


--
-- Name: testset_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testset_runs ALTER COLUMN id SET DEFAULT nextval('public.testset_runs_id_seq'::regclass);


--
-- Name: testsets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testsets ALTER COLUMN id SET DEFAULT nextval('public.test_sets_id_seq'::regclass);


--
-- Name: vault_chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_chunks ALTER COLUMN id SET DEFAULT nextval('public.vault_chunks_id_seq'::regclass);


--
-- Name: vault_reindex_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_reindex_runs ALTER COLUMN id SET DEFAULT nextval('public.vault_reindex_runs_id_seq'::regclass);


--
-- Name: backtest_configs backtest_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_configs
    ADD CONSTRAINT backtest_configs_pkey PRIMARY KEY (id);


--
-- Name: backtest_jobs backtest_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_jobs
    ADD CONSTRAINT backtest_jobs_pkey PRIMARY KEY (id);


--
-- Name: backtest_jobs backtest_jobs_result_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_jobs
    ADD CONSTRAINT backtest_jobs_result_id_key UNIQUE (result_id);


--
-- Name: backtest_result_orders backtest_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_orders
    ADD CONSTRAINT backtest_orders_pkey PRIMARY KEY (id);


--
-- Name: backtest_result_params backtest_params_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_params
    ADD CONSTRAINT backtest_params_pkey PRIMARY KEY (id);


--
-- Name: backtest_result_positions backtest_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_positions
    ADD CONSTRAINT backtest_positions_pkey PRIMARY KEY (id);


--
-- Name: backtest_results backtest_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_pkey PRIMARY KEY (id);


--
-- Name: backtest_results backtest_results_run_id_params_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_run_id_params_hash_key UNIQUE (run_id, params_hash);


--
-- Name: backtest_runs backtest_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_runs
    ADD CONSTRAINT backtest_runs_pkey PRIMARY KEY (id);


--
-- Name: backtest_result_trades backtest_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_result_trades
    ADD CONSTRAINT backtest_trades_pkey PRIMARY KEY (id);


--
-- Name: chart_playground_setups chart_playground_setups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chart_playground_setups
    ADD CONSTRAINT chart_playground_setups_pkey PRIMARY KEY (id);


--
-- Name: indicator_configs indicator_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.indicator_configs
    ADD CONSTRAINT indicator_configs_pkey PRIMARY KEY (id);


--
-- Name: leaderboard_entries leaderboard_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leaderboard_entries
    ADD CONSTRAINT leaderboard_entries_pkey PRIMARY KEY (id);


--
-- Name: ohlc_download_jobs ohlc_download_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ohlc_download_jobs
    ADD CONSTRAINT ohlc_download_jobs_pkey PRIMARY KEY (id);


--
-- Name: strategy_concepts strategy_concepts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_concepts
    ADD CONSTRAINT strategy_concepts_pkey PRIMARY KEY (id);


--
-- Name: strategy_configs strategy_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_configs
    ADD CONSTRAINT strategy_configs_pkey PRIMARY KEY (id);


--
-- Name: strategy_iterations strategy_iterations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_iterations
    ADD CONSTRAINT strategy_iterations_pkey PRIMARY KEY (id);


--
-- Name: testsets test_sets_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testsets
    ADD CONSTRAINT test_sets_name_key UNIQUE (name);


--
-- Name: testsets test_sets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testsets
    ADD CONSTRAINT test_sets_pkey PRIMARY KEY (id);


--
-- Name: testset_runs testset_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testset_runs
    ADD CONSTRAINT testset_runs_pkey PRIMARY KEY (id);


--
-- Name: leaderboard_entries uq_leaderboard_testset_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leaderboard_entries
    ADD CONSTRAINT uq_leaderboard_testset_run UNIQUE (testset_run_id);


--
-- Name: strategy_concepts uq_strategy_concepts_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_concepts
    ADD CONSTRAINT uq_strategy_concepts_slug UNIQUE (slug);


--
-- Name: strategy_iterations uq_strategy_iterations_concept_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_iterations
    ADD CONSTRAINT uq_strategy_iterations_concept_version UNIQUE (concept_id, version);


--
-- Name: vault_chunks uq_vault_chunks_path_index; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_chunks
    ADD CONSTRAINT uq_vault_chunks_path_index UNIQUE (vault_path, chunk_index);


--
-- Name: vault_reindex_runs uq_vault_reindex_runs_job_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_reindex_runs
    ADD CONSTRAINT uq_vault_reindex_runs_job_id UNIQUE (job_id);


--
-- Name: vault_chunks vault_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_chunks
    ADD CONSTRAINT vault_chunks_pkey PRIMARY KEY (id);


--
-- Name: vault_reindex_runs vault_reindex_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vault_reindex_runs
    ADD CONSTRAINT vault_reindex_runs_pkey PRIMARY KEY (id);


--
-- Name: backtest_equity_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX backtest_equity_timestamp_idx ON public.backtest_result_equity USING btree ("timestamp" DESC);


--
-- Name: backtest_indicators_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX backtest_indicators_timestamp_idx ON public.backtest_result_indicators USING btree ("timestamp" DESC);


--
-- Name: idx_backtest_runs_iteration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_backtest_runs_iteration ON public.backtest_runs USING btree (iteration_id);


--
-- Name: idx_bc_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bc_default ON public.backtest_configs USING btree (is_default);


--
-- Name: idx_bc_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bc_name ON public.backtest_configs USING btree (name);


--
-- Name: idx_be_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_be_result ON public.backtest_result_equity USING btree (result_id);


--
-- Name: idx_bi_name_output; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bi_name_output ON public.backtest_result_indicators USING btree (indicator_name, indicator_output);


--
-- Name: idx_bi_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bi_result ON public.backtest_result_indicators USING btree (result_id);


--
-- Name: idx_bi_result_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bi_result_name ON public.backtest_result_indicators USING btree (result_id, indicator_name);


--
-- Name: idx_bj_rq_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bj_rq_job ON public.backtest_jobs USING btree (rq_job_id);


--
-- Name: idx_bj_run_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bj_run_status ON public.backtest_jobs USING btree (run_id, status);


--
-- Name: idx_bo_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bo_result ON public.backtest_result_orders USING btree (result_id);


--
-- Name: idx_bp_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bp_result ON public.backtest_result_positions USING btree (result_id);


--
-- Name: idx_bpa_name_value; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bpa_name_value ON public.backtest_result_params USING btree (param_name, param_value);


--
-- Name: idx_bpa_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bpa_result ON public.backtest_result_params USING btree (result_id);


--
-- Name: idx_bpa_result_param; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bpa_result_param ON public.backtest_result_params USING btree (result_id, param_name);


--
-- Name: idx_br_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_br_created ON public.backtest_runs USING btree (created_at);


--
-- Name: idx_br_strategy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_br_strategy ON public.backtest_runs USING btree (strategy_family, strategy_name);


--
-- Name: idx_br_symbol; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_br_symbol ON public.backtest_runs USING btree (symbol);


--
-- Name: idx_bt_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bt_result ON public.backtest_result_trades USING btree (result_id);


--
-- Name: idx_ic_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ic_default ON public.indicator_configs USING btree (is_default);


--
-- Name: idx_ic_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ic_name ON public.indicator_configs USING btree (name);


--
-- Name: idx_iterations_concept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_iterations_concept ON public.strategy_iterations USING btree (concept_id);


--
-- Name: idx_iterations_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_iterations_parent ON public.strategy_iterations USING btree (parent_iteration_id);


--
-- Name: idx_iterations_spec_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_iterations_spec_hash ON public.strategy_iterations USING btree (concept_id, spec_hash);


--
-- Name: idx_leaderboard_test_set_return; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leaderboard_test_set_return ON public.leaderboard_entries USING btree (testset_id, total_return_avg DESC);


--
-- Name: idx_odj_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_odj_created ON public.ohlc_download_jobs USING btree (created_at DESC);


--
-- Name: idx_odj_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_odj_status ON public.ohlc_download_jobs USING btree (status);


--
-- Name: idx_res_profit_factor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_res_profit_factor ON public.backtest_results USING btree (profit_factor);


--
-- Name: idx_res_total_return; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_res_total_return ON public.backtest_results USING btree (total_return_pct);


--
-- Name: idx_sc_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sc_default ON public.strategy_configs USING btree (is_default);


--
-- Name: idx_sc_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sc_name ON public.strategy_configs USING btree (name);


--
-- Name: ix_backtest_runs_testset_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_backtest_runs_testset_run_id ON public.backtest_runs USING btree (testset_run_id);


--
-- Name: ix_vault_chunks_vault_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vault_chunks_vault_path ON public.vault_chunks USING btree (vault_path);


--
-- Name: ix_vault_reindex_runs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_vault_reindex_runs_started_at ON public.vault_reindex_runs USING btree (started_at);


--
-- Name: vault_chunks_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX vault_chunks_embedding_hnsw ON public.vault_chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: backtest_results backtest_results_iteration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_results
    ADD CONSTRAINT backtest_results_iteration_id_fkey FOREIGN KEY (iteration_id) REFERENCES public.strategy_iterations(id);


--
-- Name: backtest_runs backtest_runs_iteration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_runs
    ADD CONSTRAINT backtest_runs_iteration_id_fkey FOREIGN KEY (iteration_id) REFERENCES public.strategy_iterations(id);


--
-- Name: backtest_runs fk_backtest_runs_testset_run_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backtest_runs
    ADD CONSTRAINT fk_backtest_runs_testset_run_id FOREIGN KEY (testset_run_id) REFERENCES public.testset_runs(id);


--
-- Name: strategy_iterations fk_strategy_iterations_concept_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_iterations
    ADD CONSTRAINT fk_strategy_iterations_concept_id FOREIGN KEY (concept_id) REFERENCES public.strategy_concepts(id);


--
-- Name: strategy_iterations fk_strategy_iterations_parent_iteration_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.strategy_iterations
    ADD CONSTRAINT fk_strategy_iterations_parent_iteration_id FOREIGN KEY (parent_iteration_id) REFERENCES public.strategy_iterations(id);


--
-- Name: testset_runs fk_testset_runs_testset_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.testset_runs
    ADD CONSTRAINT fk_testset_runs_testset_id FOREIGN KEY (testset_id) REFERENCES public.testsets(id);


--
-- PostgreSQL database dump complete
--


--
-- TimescaleDB Hypertables (manuell angehaengt: pg_dump emittiert create_hypertable nicht)
--

SELECT public.create_hypertable('public.backtest_result_equity', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
SELECT public.create_hypertable('public.backtest_result_indicators', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);

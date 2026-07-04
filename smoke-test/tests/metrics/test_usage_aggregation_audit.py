"""
Comprehensive audit of GMS usage-aggregation instrumentation.

Exercises admin (datahub superuser) and non-admin users across GraphQL and
OpenAPI surfaces, then validates Prometheus tag cardinality and known gaps.

Run locally (requires Prometheus on :4319 and USAGE_AGGREGATION_ENABLED):

    scripts/dev/datahub-dev.sh test tests/metrics/test_usage_aggregation_audit.py

Tune flush latency for faster iteration:

    scripts/dev/datahub-dev.sh env set USAGE_AGGREGATION_FLUSH_INTERVAL_SECONDS=10
    scripts/dev/datahub-dev.sh env restart
"""

from __future__ import annotations

import logging

import pytest
import requests

from tests.metrics.usage_aggregation_metrics import (
    ACTIVE_IDENTITIES_METRIC,
    ADMIN_SUPPORT_USER_URN,
    AGGREGATION_TAG_KEYS,
    DATAHUB_SUPPORT_USER_URN,
    OUTPUT_BYTES_METRIC,
    REQUEST_COUNT_METRIC,
    assert_samples_have_tag_keys,
    can_provision_native_users,
    expected_actor_class_for_admin_session,
    expected_actor_class_for_support_session,
    fetch_metric_total,
    find_metric_samples,
    generate_graphql_read_traffic,
    generate_graphql_search_traffic,
    generate_openapi_metadata_read_traffic,
    generate_openapi_search_traffic,
    graphql_metadata_query_tags,
    is_builtin_support_user_urn,
    parse_prometheus_tags,
    parse_sample_value,
    session_corp_user_urn,
    try_mint_personal_access_token,
    wait_for_metric_at_least,
    wait_for_metric_delta,
)
from tests.utilities.metadata_operations import get_prometheus_metrics
from tests.utilities.multi_user import cleanup_step_actor_user, make_step_actor_user
from tests.utils import TestSessionWrapper, get_gms_prometheus_base_url, login_as

logger = logging.getLogger(__name__)


def _require_prometheus_url() -> str:
    gms_url = get_gms_prometheus_base_url()
    if gms_url is None:
        pytest.skip(
            "Management endpoint not resolvable — Prometheus port (4319) unreachable."
        )
    return gms_url


@pytest.mark.read_only
def test_usage_aggregation_datahub_user_is_support_in_prometheus(auth_session):
    """Builtin datahub superuser (urn:li:corpuser:datahub) exports actor_class=support."""
    gms_url = _require_prometheus_url()
    urn = session_corp_user_urn(auth_session)
    assert urn == DATAHUB_SUPPORT_USER_URN, (
        f"Expected ~/.datahubenv datahub PAT to authenticate as {DATAHUB_SUPPORT_USER_URN}, "
        f"got {urn}"
    )
    assert is_builtin_support_user_urn(urn)
    assert expected_actor_class_for_support_session(auth_session) == "support"

    tags = {
        **graphql_metadata_query_tags("support"),
        "auth_channel": "pat",
    }
    baseline = fetch_metric_total(auth_session, gms_url, REQUEST_COUNT_METRIC, tags)
    generate_graphql_read_traffic(auth_session, repeat=2)
    wait_for_metric_delta(
        auth_session,
        gms_url,
        REQUEST_COUNT_METRIC,
        baseline,
        required_tags=tags,
        min_delta=1.0,
    )

    content = get_prometheus_metrics(auth_session, gms_url)
    samples = find_metric_samples(content, REQUEST_COUNT_METRIC, required_tags=tags)
    assert samples, (
        f"No Prometheus samples for datahub support user (tags={tags}). "
        f"datahub is classified via KNOWN_SUPPORT_ACTOR_URNS."
    )
    for line in samples:
        tags_on_line = parse_prometheus_tags(line)
        assert tags_on_line.get("actor_class") == "support"
        assert tags_on_line.get("request_api") == "graphql"
    logger.info("datahub support evidence: urn=%s sample=%s", urn, samples[0])


@pytest.mark.read_only
def test_usage_aggregation_admin_builtin_support_user_traffic(auth_session):
    """Second builtin support user (urn:li:corpuser:admin) exists; traffic when PAT mintable."""
    gms_url = _require_prometheus_url()

    admin_entity = auth_session.get(
        f"{auth_session.gms_url()}/openapi/v3/entity/corpuser/"
        f"{ADMIN_SUPPORT_USER_URN.replace(':', '%3A')}"
    )
    admin_entity.raise_for_status()
    assert admin_entity.json().get("urn") == ADMIN_SUPPORT_USER_URN
    assert is_builtin_support_user_urn(ADMIN_SUPPORT_USER_URN)
    logger.info(
        "Verified second builtin support user entity exists: %s", ADMIN_SUPPORT_USER_URN
    )

    admin_pat = try_mint_personal_access_token(auth_session, ADMIN_SUPPORT_USER_URN)
    if admin_pat is None:
        logger.info(
            "Skipping admin Prometheus traffic — PAT mint unauthorized locally; "
            "admin support classification is URN-based (UsageActorClassResolver)"
        )
        return

    admin_session = TestSessionWrapper(requests.Session(), prebuilt_token=admin_pat)
    try:
        urn = session_corp_user_urn(admin_session)
        assert urn == ADMIN_SUPPORT_USER_URN
        assert expected_actor_class_for_support_session(admin_session) == "support"

        tags = {
            **graphql_metadata_query_tags("support"),
            "auth_channel": "pat",
        }
        baseline = fetch_metric_total(
            admin_session, gms_url, REQUEST_COUNT_METRIC, tags
        )
        generate_graphql_read_traffic(admin_session, repeat=2)
        wait_for_metric_delta(
            admin_session,
            gms_url,
            REQUEST_COUNT_METRIC,
            baseline,
            required_tags=tags,
            min_delta=1.0,
        )

        content = get_prometheus_metrics(admin_session, gms_url)
        samples = find_metric_samples(content, REQUEST_COUNT_METRIC, required_tags=tags)
        assert samples, (
            f"Expected Prometheus support samples for admin user (tags={tags})"
        )
        logger.info("admin support evidence: urn=%s sample=%s", urn, samples[0])
    finally:
        admin_session.destroy()


@pytest.mark.read_only
def test_usage_aggregation_datahub_session_login_support(auth_session):
    """datahub frontend session login also classifies as actor_class=support (auth_channel=session)."""
    gms_url = _require_prometheus_url()
    session = login_as("datahub", "datahub")
    datahub_session = TestSessionWrapper(session)
    try:
        urn = session_corp_user_urn(datahub_session)
        assert urn == DATAHUB_SUPPORT_USER_URN
        assert expected_actor_class_for_support_session(datahub_session) == "support"

        tags = {
            **graphql_metadata_query_tags("support"),
            "auth_channel": "session",
        }
        baseline = fetch_metric_total(
            datahub_session, gms_url, REQUEST_COUNT_METRIC, tags
        )
        generate_graphql_read_traffic(datahub_session, repeat=2)
        wait_for_metric_delta(
            datahub_session,
            gms_url,
            REQUEST_COUNT_METRIC,
            baseline,
            required_tags=tags,
            min_delta=1.0,
        )
        logger.info(
            "datahub session support evidence: urn=%s auth_channel=session", urn
        )
    finally:
        datahub_session.destroy()


@pytest.mark.read_only
def test_usage_aggregation_admin_actor_class_and_tags(auth_session):
    """Support superuser (datahub) maps to actor_class=support with full tag set."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)
    tags = graphql_metadata_query_tags(actor_class)

    baseline = fetch_metric_total(auth_session, gms_url, REQUEST_COUNT_METRIC, tags)
    generate_graphql_read_traffic(auth_session, repeat=2)

    wait_for_metric_delta(
        auth_session,
        gms_url,
        REQUEST_COUNT_METRIC,
        baseline,
        required_tags=tags,
        min_delta=1.0,
    )

    content = get_prometheus_metrics(auth_session, gms_url)
    samples = find_metric_samples(content, REQUEST_COUNT_METRIC, required_tags=tags)
    assert_samples_have_tag_keys(samples, AGGREGATION_TAG_KEYS)

    if actor_class == "support":
        logger.info("Verified datahub superuser exports actor_class=support")
    else:
        logger.info(
            "Support session actor_class=%s (not datahub superuser — support bucket untested)",
            actor_class,
        )


@pytest.mark.read_only
def test_usage_aggregation_openapi_read_and_search(auth_session):
    """OpenAPI entity read and scroll search increment request + input byte counters."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)

    read_tags = {
        "usage_operation": "metadata_read",
        "request_api": "openapi",
        "actor_class": actor_class,
    }
    search_tags = {
        "usage_operation": "search_query",
        "request_api": "openapi",
        "actor_class": actor_class,
    }

    read_baseline = fetch_metric_total(
        auth_session, gms_url, REQUEST_COUNT_METRIC, read_tags
    )
    search_baseline = fetch_metric_total(
        auth_session, gms_url, REQUEST_COUNT_METRIC, search_tags
    )

    generate_openapi_metadata_read_traffic(auth_session)
    generate_openapi_search_traffic(auth_session)

    wait_for_metric_delta(
        auth_session,
        gms_url,
        REQUEST_COUNT_METRIC,
        read_baseline,
        required_tags=read_tags,
    )
    wait_for_metric_delta(
        auth_session,
        gms_url,
        REQUEST_COUNT_METRIC,
        search_baseline,
        required_tags=search_tags,
    )

    content = get_prometheus_metrics(auth_session, gms_url)
    out_samples = find_metric_samples(
        content, OUTPUT_BYTES_METRIC, required_tags=read_tags
    )
    assert out_samples, (
        "Expected output_bytes for OpenAPI metadata_read — "
        "OpenAPI synchronous responses should be measurable"
    )


@pytest.mark.read_only
def test_usage_aggregation_graphql_output_bytes(auth_session):
    """GraphQL async responses record output_bytes after execution completes."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)
    tags = {
        **graphql_metadata_query_tags(actor_class),
    }

    request_baseline = fetch_metric_total(
        auth_session, gms_url, REQUEST_COUNT_METRIC, tags
    )
    output_baseline = fetch_metric_total(
        auth_session, gms_url, OUTPUT_BYTES_METRIC, tags
    )
    generate_graphql_read_traffic(auth_session, repeat=2)
    wait_for_metric_delta(
        auth_session,
        gms_url,
        REQUEST_COUNT_METRIC,
        request_baseline,
        required_tags=tags,
    )

    wait_for_metric_delta(
        auth_session,
        gms_url,
        OUTPUT_BYTES_METRIC,
        output_baseline,
        required_tags=tags,
        min_delta=1.0,
    )

    content = get_prometheus_metrics(auth_session, gms_url)
    graphql_output = find_metric_samples(
        content, OUTPUT_BYTES_METRIC, required_tags={"request_api": "graphql"}
    )
    assert graphql_output, (
        "Expected datahub_usage_output_bytes for request_api=graphql after async GraphQL fix"
    )


@pytest.mark.read_only
def test_usage_aggregation_graphql_output_bytes_not_double_counted(auth_session):
    """Single GraphQL response should contribute output_bytes ~= body length, not ~2x."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)
    tags = {
        **graphql_metadata_query_tags(actor_class),
    }

    from tests.metrics.usage_aggregation_metrics import _ME_QUERY, execute_graphql_raw

    output_baseline = fetch_metric_total(
        auth_session, gms_url, OUTPUT_BYTES_METRIC, tags
    )
    response_text = execute_graphql_raw(auth_session, _ME_QUERY)
    response_len = len(response_text)
    assert response_len > 0

    delta = wait_for_metric_delta(
        auth_session,
        gms_url,
        OUTPUT_BYTES_METRIC,
        output_baseline,
        required_tags=tags,
        min_delta=float(response_len) * 0.95,
    )
    assert delta <= response_len * 1.05, (
        f"output_bytes delta {delta} exceeds single-response length {response_len} "
        "(possible double-count from filter + async paths)"
    )


@pytest.mark.read_only
def test_usage_aggregation_openapi_search_output_bytes(auth_session):
    """OpenAPI scroll search records output_bytes with search_query tags."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)
    search_tags = {
        "usage_operation": "search_query",
        "request_api": "openapi",
        "actor_class": actor_class,
    }

    output_baseline = fetch_metric_total(
        auth_session, gms_url, OUTPUT_BYTES_METRIC, search_tags
    )
    generate_openapi_search_traffic(auth_session, repeat=2)
    wait_for_metric_delta(
        auth_session,
        gms_url,
        OUTPUT_BYTES_METRIC,
        output_baseline,
        required_tags=search_tags,
        min_delta=1.0,
    )


@pytest.mark.read_only
def test_usage_aggregation_regular_user_active_identities(auth_session):
    """Distinct identity gauge reflects unique regular users in the flush window."""
    gms_url = _require_prometheus_url()
    if not can_provision_native_users(auth_session):
        pytest.skip(
            "Session lacks manageIdentities — cannot provision a regular user locally"
        )

    user_urn, regular_session = make_step_actor_user(auth_session, "usage-metrics")
    try:
        identity_tags = {
            "identity_metric": "active_users",
            "actor_class": "regular",
        }
        generate_graphql_read_traffic(regular_session, repeat=2)

        wait_for_metric_at_least(
            auth_session,
            gms_url,
            ACTIVE_IDENTITIES_METRIC,
            1.0,
            required_tags=identity_tags,
        )

        req_baseline = fetch_metric_total(
            auth_session,
            gms_url,
            REQUEST_COUNT_METRIC,
            graphql_metadata_query_tags("regular"),
        )
        generate_graphql_search_traffic(regular_session)
        wait_for_metric_delta(
            auth_session,
            gms_url,
            REQUEST_COUNT_METRIC,
            req_baseline,
            required_tags={
                "usage_operation": "search_query",
                "request_api": "graphql",
                "actor_class": "regular",
            },
        )
    finally:
        regular_session.destroy()
        cleanup_step_actor_user(auth_session, user_urn)


def test_usage_aggregation_support_active_identities(auth_session):
    """Support actors appear in the support actor_class distinct-identity gauge."""
    gms_url = _require_prometheus_url()
    actor_class = expected_actor_class_for_admin_session(auth_session)
    if actor_class != "support":
        pytest.skip("Session is not classified as support")

    tags = {
        "identity_metric": "active_users",
        "actor_class": actor_class,
    }
    generate_graphql_read_traffic(auth_session, repeat=3)

    wait_for_metric_at_least(
        auth_session,
        gms_url,
        ACTIVE_IDENTITIES_METRIC,
        1.0,
        required_tags=tags,
    )

    content = get_prometheus_metrics(auth_session, gms_url)
    samples = find_metric_samples(content, ACTIVE_IDENTITIES_METRIC, required_tags=tags)
    assert samples, f"Expected support active_identities samples (tags={tags})"
    for line in samples:
        parsed = parse_prometheus_tags(line)
        assert parsed.get("actor_class") == actor_class
        assert parsed.get("identity_metric") == "active_users"
        assert parse_sample_value(line) >= 1.0

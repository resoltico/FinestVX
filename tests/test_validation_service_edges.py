"""Additional tests for FinestVX validation workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from ftllexengine import make_fluent_number
from ftllexengine.diagnostics import WarningSeverity

import finestvx.validation.service as validation_module
from finestvx.core import Account, JournalTransaction, LedgerEntry, PostingSide, TransactionState
from finestvx.validation import validate_book, validate_ftl_resource, validate_transaction
from tests.support.book_factory import build_posted_transaction, build_sample_book

_POSTED_AT = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)


class TestValidationServiceEdges:
    """Coverage for report aggregation and FTL severity bridging."""

    def test_validate_book_reports_chart_and_unknown_account_failures(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Book validation returns structured findings for chart and entry issues."""
        def raise_chart_error(_accounts: object) -> None:
            msg = "broken chart"
            raise ValueError(msg)

        def accept_chart(_accounts: object) -> None:
            return None

        monkeypatch.setattr(
            validation_module,
            "validate_chart_of_accounts",
            raise_chart_error,
        )
        chart_report = validate_book(cast("Any", SimpleNamespace(accounts=(), transactions=())))
        assert chart_report.findings[0].code == "BOOK_CHART_INVALID"

        account = Account(
            code="1000",
            name="Cash",
            normal_side=PostingSide.DEBIT,
            currency="EUR",
        )
        partial_book = SimpleNamespace(
            accounts=(account,),
            transactions=(build_posted_transaction(reference="TX-2026-3000"),),
        )
        monkeypatch.setattr(validation_module, "validate_chart_of_accounts", accept_chart)

        report = validate_book(cast("Any", partial_book))

        assert {finding.code for finding in report.findings} == {
            "TRANSACTION_UNKNOWN_ACCOUNT",
            "BOOK_UNKNOWN_ACCOUNT_REFERENCE",
        }

    def test_validate_transaction_reports_balance_and_account_errors(self) -> None:
        """Transaction validation surfaces structural and referential problems."""
        draft_transaction = JournalTransaction(
            reference="TX-2026-3001",
            posted_at=_POSTED_AT,
            description="Unbalanced draft",
            state=TransactionState.DRAFT,
            entries=(
                LedgerEntry(
                    account_code="1000",
                    side=PostingSide.DEBIT,
                    amount=make_fluent_number(Decimal("10.00")),
                    currency="EUR",
                ),
            ),
        )

        balance_report = validate_transaction(build_sample_book(), draft_transaction)
        assert balance_report.findings[0].code == "TRANSACTION_BALANCE_INVALID"

        unknown_account_report = validate_transaction(
            build_sample_book(),
            build_posted_transaction(reference="TX-2026-3002"),
        )
        assert unknown_account_report.findings == ()

        partial_book = SimpleNamespace(
            accounts=(
                Account(
                    code="1000",
                    name="Cash",
                    normal_side=PostingSide.DEBIT,
                    currency="EUR",
                ),
            )
        )
        missing_account_report = validate_transaction(
            cast("Any", partial_book),
            build_posted_transaction(reference="TX-2026-3003"),
        )
        assert missing_account_report.findings[0].code == "TRANSACTION_UNKNOWN_ACCOUNT"

    def test_warning_severity_mapping_and_ftl_annotation_reporting(self) -> None:
        """Static FTL validation maps warnings and junk annotations into reports."""
        assert validation_module._severity_from_warning(WarningSeverity.CRITICAL).value == "error"
        assert validation_module._severity_from_warning(WarningSeverity.WARNING).value == "warning"
        assert validation_module._severity_from_warning(WarningSeverity.INFO).value == "info"

        warning_report = validate_ftl_resource("hello = one\nhello = two\n")
        annotation_report = validate_ftl_resource("broken = {\n")

        assert any(finding.severity.value == "warning" for finding in warning_report.findings)
        assert any(finding.code == "PARSE_JUNK" for finding in annotation_report.findings)

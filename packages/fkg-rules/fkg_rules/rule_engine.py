"""
Rule Engine — validates AI agent outputs against a deterministic rule set.

Design principles:
- Rules are defined in YAML files, NOT in Python code.
- Rules are hot-reloadable without service restart.
- Every rule violation is recorded with rule_id, severity, field, and value.
- Severity levels: ERROR (block), WARNING (flag), INFO (log only).
- The rule engine is STATELESS — it receives data, returns violations.

Why not a validation framework like Great Expectations?
- Our rules are domain-specific (food knowledge), not generic data quality.
- We need custom cross-field rules (e.g. protein < serving_size).
- YAML rules allow non-engineers to add new rules without code changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
import yaml

log = structlog.get_logger()


class RuleSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class RuleViolation:
    """A single rule violation detected during validation."""

    rule_id: str
    rule_name: str
    severity: RuleSeverity
    message: str
    field: str | None = None
    value: Any = None

    @property
    def is_blocking(self) -> bool:
        """ERROR severity violations block the record from entering the graph."""
        return self.severity == RuleSeverity.ERROR


@dataclass
class ValidationResult:
    """The complete result of running the rule engine against one record."""

    passed: bool
    violations: list[RuleViolation] = field(default_factory=list)
    errors: list[RuleViolation] = field(default_factory=list)
    warnings: list[RuleViolation] = field(default_factory=list)

    def has_error(self, rule_id: str) -> bool:
        return any(v.rule_id == rule_id for v in self.errors)

    def has_warning(self, rule_id: str) -> bool:
        return any(v.rule_id == rule_id for v in self.warnings)


class RuleEngine:
    """
    Loads and executes validation rules against structured dish/cuisine/country data.

    Usage:
        engine = RuleEngine(rules_dir="packages/fkg-rules/fkg_rules/rules/")
        result = engine.validate_dish(dish_output)
        if not result.passed:
            send_to_review_queue(dish_output, result)
    """

    # Allowed values for enumerated fields — enforced by rule TAX_002
    VALID_MEAL_TYPES = {
        "breakfast", "brunch", "lunch", "dinner", "snack",
        "dessert", "beverage", "street_food", "festival",
    }
    VALID_DISH_CATEGORIES = {
        "traditional", "street_food", "festival_food", "everyday",
        "celebratory", "historical", "royal", "religious",
    }

    def __init__(self, rules_dir: str | None = None) -> None:
        self._rules: list[dict] = []
        if rules_dir:
            self._load_rules(rules_dir)

    def _load_rules(self, rules_dir: str) -> None:
        """Load all YAML rule files from the rules directory."""
        import pathlib

        rules_path = pathlib.Path(rules_dir)
        for yaml_file in rules_path.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if data and "rules" in data:
                    self._rules.extend(data["rules"])
                    log.info("rule_engine.loaded", file=yaml_file.name, count=len(data["rules"]))

    def validate_dish(self, dish_data: dict) -> ValidationResult:
        """Validate a dish output dictionary against all registered rules.

        Args:
            dish_data: Dictionary representation of a DishOutput.

        Returns:
            ValidationResult with all violations categorized by severity.
        """
        violations: list[RuleViolation] = []

        # ── Hardcoded critical rules (always run, cannot be disabled) ──────────
        violations.extend(self._run_critical_rules(dish_data))

        # ── YAML-defined rules ─────────────────────────────────────────────────
        for rule in self._rules:
            violation = self._evaluate_rule(rule, dish_data)
            if violation:
                violations.append(violation)

        errors = [v for v in violations if v.severity == RuleSeverity.ERROR]
        warnings = [v for v in violations if v.severity == RuleSeverity.WARNING]

        return ValidationResult(
            passed=len(errors) == 0,
            violations=violations,
            errors=errors,
            warnings=warnings,
        )

    def _run_critical_rules(self, data: dict) -> list[RuleViolation]:
        """Execute hardcoded critical rules that protect graph integrity.

        These rules are hardcoded (not YAML) because they are foundational
        invariants that must NEVER be disabled. YAML rules can be misconfigured;
        these cannot.
        """
        violations = []
        nutrition = data.get("nutrition") or {}

        # NUT_001: Calories cannot be negative
        calories = nutrition.get("calories_kcal")
        if calories is not None and calories < 0:
            violations.append(RuleViolation(
                rule_id="NUT_001",
                rule_name="calories_non_negative",
                severity=RuleSeverity.ERROR,
                message="Calories cannot be negative",
                field="nutrition.calories_kcal",
                value=calories,
            ))

        # NUT_002: Protein cannot exceed serving size
        protein = nutrition.get("protein_g")
        serving = nutrition.get("per_serving_g")
        if protein is not None and serving is not None and protein > serving:
            violations.append(RuleViolation(
                rule_id="NUT_002",
                rule_name="protein_weight_bound",
                severity=RuleSeverity.ERROR,
                message=f"Protein ({protein}g) cannot exceed total serving size ({serving}g)",
                field="nutrition.protein_g",
                value=protein,
            ))

        # COMP_001: Dish name is mandatory
        if not data.get("name"):
            violations.append(RuleViolation(
                rule_id="COMP_001",
                rule_name="dish_name_required",
                severity=RuleSeverity.ERROR,
                message="Dish name is mandatory and cannot be empty",
                field="name",
                value=None,
            ))

        # COMP_002: Cuisine hint is mandatory
        if not data.get("cuisine_hint"):
            violations.append(RuleViolation(
                rule_id="COMP_002",
                rule_name="cuisine_required",
                severity=RuleSeverity.ERROR,
                message="Every dish must be linked to a cuisine",
                field="cuisine_hint",
                value=None,
            ))

        # TAX_001: At least one meal type must be specified
        if not data.get("meal_types"):
            violations.append(RuleViolation(
                rule_id="TAX_001",
                rule_name="meal_type_required",
                severity=RuleSeverity.ERROR,
                message="Dish must have at least one meal type",
                field="meal_types",
                value=None,
            ))

        # TAX_002: Meal types must be from allowed set
        for mt in data.get("meal_types", []):
            if mt not in self.VALID_MEAL_TYPES:
                violations.append(RuleViolation(
                    rule_id="TAX_002",
                    rule_name="valid_meal_type",
                    severity=RuleSeverity.ERROR,
                    message=f"Meal type '{mt}' is not in the allowed set",
                    field="meal_types",
                    value=mt,
                ))

        # TAX_003: Vegan dishes must also be vegetarian
        dietary = data.get("dietary") or {}
        if dietary.get("is_vegan") is True and dietary.get("is_vegetarian") is False:
            violations.append(RuleViolation(
                rule_id="TAX_003",
                rule_name="vegan_implies_vegetarian",
                severity=RuleSeverity.ERROR,
                message="A vegan dish cannot be marked non-vegetarian",
                field="dietary.is_vegetarian",
                value=False,
            ))

        # CONF_001: Confidence score must be present and valid
        confidence = data.get("confidence")
        if confidence is None or not (0.0 <= confidence <= 1.0):
            violations.append(RuleViolation(
                rule_id="CONF_001",
                rule_name="confidence_valid",
                severity=RuleSeverity.ERROR,
                message="Confidence score must be between 0.0 and 1.0",
                field="confidence",
                value=confidence,
            ))

        return violations

    def _evaluate_rule(self, rule: dict, data: dict) -> RuleViolation | None:
        """Evaluate a single YAML-defined rule against data.

        Rules use a simple dot-notation field path and Python expression conditions.
        Example rule YAML:
            id: NUT_003
            name: macro_sum_reasonable
            severity: warning
            field: nutrition
            condition: "macros_kcal <= calories * 1.2"
        """
        try:
            rule_id = rule["id"]
            severity = RuleSeverity(rule.get("severity", "warning"))
            condition_str = rule.get("condition", "")

            # Build eval context from flat data dict
            ctx = self._build_eval_context(data)

            # Evaluate condition — returns True if rule PASSES
            result = eval(condition_str, {"__builtins__": {}}, ctx)  # noqa: S307

            if not result:
                return RuleViolation(
                    rule_id=rule_id,
                    rule_name=rule.get("name", rule_id),
                    severity=severity,
                    message=rule.get("message", f"Rule {rule_id} violated"),
                    field=rule.get("field"),
                    value=ctx.get(rule.get("field", ""), None),
                )
        except Exception as exc:
            log.warning("rule_engine.eval_error", rule_id=rule.get("id"), error=str(exc))

        return None

    def _build_eval_context(self, data: dict) -> dict:
        """Flatten nested dict into eval context with safe defaults."""
        ctx: dict = {}
        nutrition = data.get("nutrition") or {}

        ctx["calories"] = nutrition.get("calories_kcal") or 0
        ctx["protein_g"] = nutrition.get("protein_g") or 0
        ctx["fat_g"] = nutrition.get("fat_g") or 0
        ctx["carbs_g"] = nutrition.get("carbohydrates_g") or 0
        ctx["serving_g"] = nutrition.get("per_serving_g") or 0
        ctx["macros_kcal"] = (ctx["protein_g"] + ctx["fat_g"] + ctx["carbs_g"]) * 4
        ctx["confidence"] = data.get("confidence") or 0
        ctx["name"] = data.get("name") or ""
        ctx["description"] = data.get("description") or ""
        ctx["len"] = len

        return ctx

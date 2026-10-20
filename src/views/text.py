"""Terminal view of a conversion plan."""

from .. import codec


def render(plan, verbose=False):
    """Return printable lines describing what a conversion would do."""
    lines = [
        f"Plan for {plan.source}",
        "=" * 76,
    ]
    for label, value in plan.summary().items():
        lines.append(f"  {label:<36} {value:>8}")

    lines.append("")
    lines.append(
        "  READY -- nothing left to a guess"
        if plan.is_ready()
        else "  NOT READY -- decisions are still being guessed at (see below)"
    )

    undecided = plan.undecided()
    if undecided:
        lines += [
            "",
            "Referenced but not present -- needs a substitute or a tagset",
            "-" * 76,
        ]
        for ref in undecided[: (None if verbose else 15)]:
            best = f"  suggest: {ref.candidates[0][0]}" if ref.candidates else ""
            lines.append(
                f" {ref.label:<12} referenced {ref.references:>3} time(s)"
                f"{best}"
            )
        if not verbose and len(undecided) > 15:
            lines.append(f" ... and {len(undecided) - 15} more (use --verbose)")

    review = plan.needs_review()
    if review:
        lines += [
            "",
            "Synthesised mesh fields worth a look",
            "-" * 76,
        ]
        for field in review:
            lines.append(
                f" {field.name:<26} = {field.value!r:<14} "
                f"({field.agreed}/40 reference meshes agreed)"
            )
            # What it is and what the number means -- a bare scaled integer is
            # not something a reader can form a view about.
            if field.summary:
                lines.append(f"   {field.label}: {field.summary}")
            if field.human_value != str(field.value):
                lines.append(f"   = {field.human_value}")
            if field.range_warning:
                lines.append(f"   ! {field.range_warning}")

    lines += ["", "Tags by type", "-" * 76]
    for tag_type, counts in plan.by_tag_type().items():
        lines.append(
            f" {codec.decode_string(tag_type):<6} "
            f"{counts['converted']:>4} converted  "
            f"{counts['passed-through']:>4} passed through"
        )

    if plan.entrypoints:
        lines += ["", f"Levels the game will list ({len(plan.entrypoints)})", "-" * 76]
        shown = plan.entrypoints if verbose else plan.entrypoints[:10]
        for record in shown:
            lines.append(
                f" {codec.decode_string(record.entry_id):<6} "
                f"{codec.decode_string(record.entry_long_name)}"
            )
        if not verbose and len(plan.entrypoints) > 10:
            lines.append(f" ... and {len(plan.entrypoints) - 10} more (use --verbose)")

    if plan.warnings:
        lines += ["", "Warnings", "-" * 76]
        for warning in plan.warnings:
            lines.append(f" ! {warning}")

    return lines

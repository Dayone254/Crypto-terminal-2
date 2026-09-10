"""Top Picker Terminal — CLI entry point."""
from __future__ import annotations

import asyncio
import json

import typer

app = typer.Typer(name="tpt", help="Top Picker Terminal — crypto market scanner.")


def _format_price(val: float | None) -> str:
    if val is None:
        return "-"
    if val < 0.0001:
        return f"${val:.6f}"
    elif val < 1.0:
        return f"${val:.5f}"
    elif val < 10.0:
        return f"${val:.3f}"
    else:
        return f"${val:.2f}"


def _format_vol(val: float | None) -> str:
    if val is None or val == 0:
        return "$0"
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.2f}B"
    elif val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"${val / 1_000:.1f}K"
    else:
        return f"${val:.0f}"


@app.command()
def scan(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print scan plan without running."),
    output: str = typer.Option("table", "--output", help="Output format: table | json"),
    min_volume: float = typer.Option(1_000_000.0, "--min-vol", help="Minimum 24h quote volume filter"),
) -> None:
    """Run an on-demand market scan across active Coinbase USD products."""
    from tpt.scanner.runner import run_scan

    if dry_run:
        typer.echo("[DRY RUN] Will scan active Coinbase USD spot products.")
        typer.echo(f"[DRY RUN] Minimum quote volume threshold: {_format_vol(min_volume)}")
        return

    typer.echo("Scanning Coinbase USD spot markets...")
    result = asyncio.run(run_scan(trigger="ON_DEMAND"))

    if result.status == "FAILED":
        typer.secho(f"Scan failed: {result.error_message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if output == "json":
        typer.echo(json.dumps(result.candidates, indent=2))
        return

    # Table output using rich (or fall back to clean text formatting)
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Top Picker Terminal — Scan Run {result.scan_run_id[:8]} ({result.duration_seconds}s)")

        table.add_column("Symbol", style="bold cyan")
        table.add_column("Last", justify="right")
        table.add_column("24h %", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Label", style="bold")
        table.add_column("PIR", justify="right")
        table.add_column("Quote Vol", justify="right")
        table.add_column("Tranche A", justify="right", style="green")
        table.add_column("Tranche B", justify="right", style="green")

        for c in result.candidates:
            # Filter out low-volume WATCH symbols for cleaner CLI view if desired
            lbl = c["label"]
            score = c["composite_score"]
            last = _format_price(c["last_price"])
            chg = c["day_change_pct"]
            chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
            pir = f"{c['pos_in_range']:.2f}"
            qvol = _format_vol(c["quote_vol_24h"])

            lad = c.get("ladder")
            tr_a = _format_price(lad["tranche_a_price"]) if lad else "-"
            tr_b = _format_price(lad["tranche_b_price"]) if lad else "-"

            # Color styling per label
            if lbl == "ENTRY_ZONE":
                lbl_str = f"[bold green]{lbl}[/bold green]"
            elif lbl == "COILED":
                lbl_str = f"[bold yellow]{lbl}[/bold yellow]"
            elif lbl == "EARLY":
                lbl_str = f"[bold cyan]{lbl}[/bold cyan]"
            elif lbl == "CHASE":
                lbl_str = f"[bold magenta]{lbl}[/bold magenta]"
            elif lbl == "SKIP":
                lbl_str = f"[dim]{lbl}[/dim]"
            else:
                lbl_str = f"[white]{lbl}[/white]"

            if c.get("pinned"):
                lbl_str += " 📌"

            table.add_row(
                c["product_id"],
                last,
                chg_str,
                f"{score:.0f}",
                lbl_str,
                pir,
                qvol,
                tr_a,
                tr_b,
            )

        console.print(table)
        console.print(
            f"Fetched: {result.symbols_fetched} products | Stale: {result.symbols_stale} | Candidates: {result.candidates_count}"
        )

    except ImportError:
        # Simple plain text table fallback
        print(f"\nScan Run {result.scan_run_id[:8]} ({result.duration_seconds}s)")
        header = f"{'Symbol':<12} {'Last':<10} {'24h %':<10} {'Score':<8} {'Label':<12} {'PIR':<6} {'Quote Vol':<12} {'Tranche A':<10} {'Tranche B':<10}"
        print(header)
        print("-" * len(header))

        for c in result.candidates:
            lad = c.get("ladder")
            tr_a = _format_price(lad["tranche_a_price"]) if lad else "-"
            tr_b = _format_price(lad["tranche_b_price"]) if lad else "-"
            chg = c["day_change_pct"]
            chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
            row = (
                f"{c['product_id']:<12} "
                f"{_format_price(c['last_price']):<10} "
                f"{chg_str:<10} "
                f"{c['composite_score']:<8.0f} "
                f"{c['label']:<12} "
                f"{c['pos_in_range']:<6.2f} "
                f"{_format_vol(c['quote_vol_24h']):<12} "
                f"{tr_a:<10} "
                f"{tr_b:<10}"
            )
            print(row)


watch_app = typer.Typer(help="Manage pinned watchlist symbols.")
app.add_typer(watch_app, name="watch")


@watch_app.command("add")
def watch_add(product_id: str = typer.Argument(..., help="Symbol e.g. ZORA-USD")) -> None:
    """Pin a symbol to the watchlist."""
    from tpt.db.connection import AsyncSessionLocal, init_db
    from tpt.db.queries import add_to_watchlist

    async def _add():
        await init_db()
        async with AsyncSessionLocal() as db:
            sym = await add_to_watchlist(db, product_id.upper())
            typer.secho(f"[PIN] Pinned {sym.product_id} to watchlist.", fg=typer.colors.GREEN)

    asyncio.run(_add())


@watch_app.command("remove")
def watch_remove(product_id: str = typer.Argument(..., help="Symbol e.g. ZORA-USD")) -> None:
    """Unpin a symbol from the watchlist."""
    from tpt.db.connection import AsyncSessionLocal, init_db
    from tpt.db.queries import remove_from_watchlist

    async def _remove():
        await init_db()
        async with AsyncSessionLocal() as db:
            ok = await remove_from_watchlist(db, product_id.upper())
            if ok:
                typer.secho(f"Removed {product_id.upper()} from watchlist.", fg=typer.colors.YELLOW)
            else:
                typer.secho(f"Symbol {product_id.upper()} not found in watchlist.", fg=typer.colors.RED)

    asyncio.run(_remove())


@watch_app.command("list")
def watch_list() -> None:
    """List all pinned watchlist symbols."""
    from tpt.db.connection import AsyncSessionLocal, init_db
    from tpt.db.queries import get_watchlist

    async def _list():
        await init_db()
        async with AsyncSessionLocal() as db:
            symbols = await get_watchlist(db)
            if not symbols:
                typer.echo("No pinned watchlist symbols.")
                return
            typer.echo(f"Pinned Watchlist ({len(symbols)} symbols):")
            for s in symbols:
                typer.echo(f" - [PIN] {s.product_id} ({s.display_name})")

    asyncio.run(_list())


@app.command()
def ladder(product_id: str = typer.Argument(..., help="Symbol e.g. ZORA-USD")) -> None:
    """Display latest computed limit-ladder levels and formatted copy template for a symbol."""
    from tpt.db.connection import AsyncSessionLocal, init_db
    from tpt.db.queries import get_latest_ladder_and_score
    from tpt.engine.ladder import format_ladder_text

    async def _ladder():
        await init_db()
        async with AsyncSessionLocal() as db:
            data = await get_latest_ladder_and_score(db, product_id.upper())
            if not data:
                typer.secho(f"No scan data found for symbol '{product_id.upper()}'. Run 'tpt scan' first.", fg=typer.colors.RED)
                raise typer.Exit(code=1)

            lad = data.get("ladder")
            if not lad:
                typer.secho(f"No active ladder for {product_id.upper()} (Label: {data['label']}, Score: {data['composite_score']:.0f}).", fg=typer.colors.YELLOW)
                return

            text = format_ladder_text(
                product_id=data["product_id"],
                score_val=data["composite_score"],
                lbl=data["label"],
                ladder=lad,
            )
            typer.echo("\n" + text + "\n")

    asyncio.run(_ladder())


@app.command()
def serve() -> None:
    """Start the FastAPI backend server."""
    import uvicorn

    from tpt.config.settings import settings
    uvicorn.run("tpt.api.main:app", host=settings.api_host, port=settings.api_port, reload=True)


if __name__ == "__main__":
    app()

"""Write reports/source_expansion.md from the catalog, the runner probe, the terms review and the measured metrics.

Usage: python scripts/build_source_report.py
"""

import csv
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import source_catalog  # noqa: E402

REPORTS = PROJECT_DIR / "reports"


def cell(value):
    return str(value).replace("|", "/").replace("\n", " ")


def source_table(rows, probe_by_name):
    lines = ["| Kaynak | source_type | status | yöntem | çalıştırıcı HTTP | 7 g öğe | havacılık filtresi | ≥ min_score 40 | listeye giren | dil | commercial_use_risk | basis |",
             "|---|---|---|---|--:|--:|--:|--:|--:|---|---|---|"]
    for row in rows:
        record = probe_by_name[row["name"]]
        basis = "headline_only" if row["mode"] == "feed_only" else "—"
        lines.append("| " + " | ".join(cell(value) for value in (
            row["name"], row["source_type"], row["status"], record["method"] or "—", record["http_code"] or "—", record["items_7d"], record.get("aviation_passed", 0),
            record.get("above_min_score", 0), record.get("listed", 0), row["language"], row["commercial_use_risk"] or "—", basis)) + " |")
    return lines


def legal_section(rows, terms):
    lines = ["## Ücretli katman öncesi hukuki değerlendirme gerektiren kaynaklar", "",
             "`commercial_use_risk = high` veya `medium` olan kaynaklar. Risk kaynağı pasif yapmaz, yalnızca kayda geçer. **Okundu** sütunu: şart sayfası bu çalışmada gerçekten okundu mu? "
             "Hayır ise bulgu doğrulanmamıştır (sayfa erişilemedi, arama özeti ya da bellek) ve bir insan tarafından kontrol edilmelidir.", ""]
    for risk, title in (("high", "Yüksek risk (şartlar ticari kullanımı, yeniden dağıtımı veya otomatik erişimi kısıtlıyor)"), ("medium", "Orta risk (belirsiz ya da okunamadı)")):
        group = [row for row in rows if row["commercial_use_risk"] == risk]
        lines += [f"### {title} — {len(group)} kaynak", "", "| Kaynak | status | Okundu | Şartın kısa özeti | Bağlantı |", "|---|---|---|---|---|"]
        for row in group:
            review = terms["sources"][row["name"]]
            link = review["terms_url"] or "—"
            lines.append(f"| {cell(row['name'])} | {row['status']} | {'evet' if review['read'] else 'hayır'} | {cell(review['summary'])} | {link} |")
        lines.append("")
    return lines


def main():
    rows = source_catalog.read_rows()
    probe = json.loads((REPORTS / "source_probe.json").read_text(encoding="utf-8"))
    terms = json.loads((PROJECT_DIR / "config" / "source_terms_review.json").read_text(encoding="utf-8"))
    metrics = json.loads((REPORTS / "source_expansion_metrics.json").read_text(encoding="utf-8"))
    probe_by_name = {record["name"]: record for record in probe["sources"]}
    by_status = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    before, after = metrics["before"], metrics["after"]
    cluster = metrics["clustering_validation"]
    lines = [
        "# Kaynak genişletme raporu", "",
        f"Çalıştırıcı sondası: {probe['generated_at']} ({probe['runner']['platform']}, Python {probe['runner']['python']}), süre {probe['duration_seconds']} sn. "
        f"User-Agent: `{probe['user_agent']}`. Ham çıktı: `reports/source_probe.json`; doğrulanan besleme adresleri: `config/feeds_discovered.json`; şart incelemesi: `config/source_terms_review.json`.", "",
        "## Özet", "",
        f"- Katalogda {len(rows)} kaynak var; durumlar: " + ", ".join(f"{status} {count}" for status, count in sorted(by_status.items())) + ".",
        "- Tek User-Agent (kişisel e-posta yok, tarayıcı kimliği yok), robots.txt (joker karakter destekli), alan adı başına sıralı çekim ve koşullu istek uygulanıyor; makale sayfası çekilmiyor.",
        "- `feed_only` kaynaklarda yalnızca yayıncının halka açık RSS/Atom beslemesi kullanılır (site haritası, JSON-LD ve sayfa kazıma yok). Besleme özeti yalnızca modele bir kez verilir, arşive yazılmaz, API'de dönmez; anlatıdan, başlıkta ve özette olmayan her sayı silinir.",
        "- Sondanın getirdiği değişiklik büyük: tarayıcı kimliğini bırakıp dürüst User-Agent'a geçince daha önce okunan birkaç resmî haber odası da 403/zaman aşımı vermeye başladı (Air Canada, Qantas, Japan Airlines, JetBlue, LATAM, Copa, FlightGlobal, Turkish Airlines Blog ve diğerleri). Bunlar `disabled_blocked` olarak, HTTP koduyla ve sebebiyle listede duruyor.",
        "- SEC EDGAR: altı şirketin hepsi 403 veriyor. SEC adil erişim politikası User-Agent içinde iletişim e-postası istiyor; proje kuralı kişisel e-posta yasakladığı için bu kaynaklar kapalı. Çözüm kararı kullanıcıda (örneğin proje için ayrılmış, kişisel olmayan bir adres).", "",
        "## Kaynak başına sonuç", ""] + source_table(rows, probe_by_name) + ["",
        "`7 g öğe`: son 7 günde besleme/sayfadan gelen öğe. `havacılık filtresi`: sıkı havacılık filtresinden (genel beslemelerde) geçen. `≥ min_score 40`: öğenin hikâyesinin skoru 40 ve üstü. `listeye giren`: bu hikâyelerden savunma ve yatırım yorumu süzgecinden de geçenler. Skorlama DEĞİŞTİRİLMEDİ; ağırlıklar ve eşikler aynen duruyor.", "",
        "## Aktif kaynak sayısı önce / sonra", "",
        "| | Önce (main) | Sonra (bu dal) |", "|---|--:|--:|",
        f"| Katalogda aktif | {before['sources_in_catalog_active']} | {after['sources_in_catalog_active']} |",
        f"| Hatasız okunan (tek geçiş, bu bilgisayar) | kaydedilmedi | {after['sources_read_without_error']} |", "",
        "Önceki sürüm kaynak başına sonuç tutmuyordu; bu yüzden \"önce\" için yalnızca katalog sayısı var. Katalogdaki 36 aktif kaynağın 12'si GitHub çalıştırıcısında her çalışmada atlanıyordu (önceki rapor).", "",
        "## Günlük hikâye sayısı önce / sonra", "",
        f"{metrics['_doc']}", "",
        "| Kademe | Önce | Sonra |", "|---|--:|--:|",
    ]
    for level, label in (("critical", "Critical"), ("important", "Important"), ("watch", "Watch")):
        lines.append(f"| {label} | {before['listed_by_level'].get(level, 0)} | {after['listed_by_level'].get(level, 0)} |")
    lines += [f"| Toplam (listede) | {before['listed_total']} | {after['listed_total']} |",
              f"| Makale / aday hikâye | {before['articles']} / {before['candidates']} | {after['articles']} / {after['candidates']} |", "",
              "## tech_vendor gürültüsü", "",
              f"Aktif tech_vendor: {', '.join(metrics['tech_vendor']['active'])}. 7 günde {metrics['tech_vendor']['items_7d']} öğe, {metrics['tech_vendor']['pass_aviation_filter']} tanesi havacılık filtresinden geçti, "
              f"{metrics['tech_vendor']['above_min_score']} tanesi min_score üstüne çıktı, {metrics['tech_vendor']['listed']} tanesi listeye girdi. Önerilen güvenilirlik: {metrics['tech_vendor']['suggested_reliability']}. "
              "PROS, Amadeus, Sabre ve T2RL'de halka açık besleme bulunamadı (PROS ayrıca robots.txt ile `*/feed` yolunu yasaklıyor).", "",
              "## Çalışma süresi ve Gemini", "",
              f"- Toplama geçişi (tüm kaynaklar, bu bilgisayar): {after['seconds']} sn (önce {before['seconds']} sn).",
              f"- Tam çalışma (toplama + anlatı + yayın hazırlığı, kuru çalıştırma, gerçek Gemini): {metrics['full_run_with_narratives']['seconds']} sn; **Gemini çağrısı {metrics['full_run_with_narratives']['gemini_calls']}** "
              f"(çalışma başına üst sınır 2, çağrı başına 8 hikâye; {metrics['full_run_with_narratives']['stories_narrated']} hikâye anlatıldı).",
              f"- Sonda iş akışı (95 kaynak, GitHub çalıştırıcısı): {metrics['probe_workflow_seconds_on_runner']} sn; zaman sınırı 30 dk.", "",
              "## Kümeleme doğrulaması", "",
              "Aynı olayın farklı kaynak türlerinden kopyalarının tek hikâyede birleştiği gerçek örnekler:", "",
              "| Hikâye | Türler | Birleşen kaynaklar | Kaynak |", "|---|---|---|---|"]
    for example in cluster["merged_examples"]:
        lines.append(f"| `{example['story_id']}` {cell(example['headline'])} | {', '.join(example['kinds'])} | {', '.join(example['sources'])} | {example['origin']} |")
    lines += ["", f"Düzenleyici + basın: {cluster['regulator_with_press']}.", "", "Birleşmeyen örnekler (kural genişletilmedi):", ""]
    for miss in cluster["not_merged"]:
        lines.append(f"- {miss['why']}: «{miss['a']}» ↔ «{miss['b']}» (ortak sözcükler: {', '.join(miss['shared'])})")
    lines += ["", f"Kümeleme kuralı değişikliği: {cluster['rule_change']}.", ""] + legal_section(rows, terms)
    (REPORTS / "source_expansion.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"reports/source_expansion.md: {len(lines)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())

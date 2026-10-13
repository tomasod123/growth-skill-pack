#!/usr/bin/env tsx
// Enrich leads with LinkedIn profile data via RapidAPI LinkedIn Bulk Scraper.
// WARNING: LinkedIn ToS restricts scraping. Use at your own legal risk.
// Run: npx tsx scripts/enrichments/linkedin-profile.ts --input leads.csv --output leads-li.csv

import { env, required, parseArgs, readCsv, writeCsv, createQueue, retry } from "../_lib.ts";

async function main() {
  const { flags } = parseArgs();
  const input = (flags.input as string) || "leads.csv";
  const output = (flags.output as string) || "leads-li.csv";

  const key = required("RAPIDAPI_KEY");

  const leads = readCsv(input);
  console.log(`Enriching ${leads.length} leads with LinkedIn profile data...`);
  console.log("⚠️  Legal note: LinkedIn ToS restricts scraping. You are responsible for compliance.");

  const queue = createQueue(5);
  const errors: any[] = [];
  let enriched = 0;

  const enriched_rows = await Promise.all(leads.map(lead => queue.add(async () => {
    if (!lead.linkedin_url) return { ...lead };
    try {
      const res = await retry(() => fetch("https://linkedin-bulk-data-scraper.p.rapidapi.com/person", {
        method: "POST",
        headers: {
          "X-RapidAPI-Key": key,
          "X-RapidAPI-Host": "linkedin-bulk-data-scraper.p.rapidapi.com",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ link: lead.linkedin_url }),
      }));
      if (!res.ok) {
        errors.push({ email: lead.email, error: `HTTP ${res.status}` });
        return { ...lead };
      }
      const j: any = await res.json();
      const p = j?.data || j;
      if (p) {
        enriched++;
        return {
          ...lead,
          linkedin_headline: p.headline || "",
          linkedin_about: (p.about || "").slice(0, 500),
          linkedin_tenure_years: p.currentTenureYears || "",
        };
      }
      return { ...lead };
    } catch (e: any) {
      errors.push({ email: lead.email, error: e.message });
      return { ...lead };
    }
  })));

  writeCsv(output, enriched_rows);
  if (errors.length > 0) writeCsv("linkedin-profile-errors.csv", errors);

  console.log(`\n✅ Enriched ${enriched}/${leads.length} with LinkedIn data (${errors.length} errors)`);
  console.log(`Saved to ${output}`);
}

main().catch(e => { console.error(e); process.exit(1); });

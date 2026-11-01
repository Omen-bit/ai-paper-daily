// Run with: node --experimental-strip-types --test supabase/tests/breakdown.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cleanHeading, numbersIn, parseBreakdown, parseSummary, summaryInput, textOf, tidyTex, worthShowing,
} from "../functions/_shared/breakdown.ts";

// A page in the layout arXiv's HTML (LaTeXML) uses
const PAGE = `<!DOCTYPE html><html><body><article class="ltx_document">
<h1 class="ltx_title ltx_title_document">Tiny Speech</h1>
<div class="ltx_abstract"><p class="ltx_p">We distil speech models.</p></div>
<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
<div class="ltx_para"><p class="ltx_p">Speech recognition on phones is hard <cite class="ltx_cite">[<a href="#bib.bib1">1</a>]</cite>.</p></div>
<div class="ltx_para"><p class="ltx_p">Our contributions are as follows:</p>
<ul id="S1.I1" class="ltx_itemize">
<li id="S1.I1.i1" class="ltx_item"><span class="ltx_tag ltx_tag_item">•</span><div class="ltx_para"><p class="ltx_p">We cut memory use by <math alttext="48\\%" display="inline"><mn>48</mn></math> with a distillation loss.</p></div></li>
<li id="S1.I1.i2" class="ltx_item"><span class="ltx_tag ltx_tag_item">•</span><div class="ltx_para"><p class="ltx_p">We release code at <a href="https://github.com/ana/tiny-speech">https://github.com/ana/tiny-speech</a>.</p></div></li>
</ul></div></section>
<section id="S4" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag">4 </span>Experiments</h2>
<figure id="S4.T1" class="ltx_table"><figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_table">Table 1: </span>Word error rate on LibriSpeech.</figcaption>
<div class="ltx_inline-block"><table class="ltx_tabular"><thead><tr class="ltx_tr"><th class="ltx_th">Model</th><th class="ltx_th">WER</th></tr></thead>
<tbody><tr class="ltx_tr"><td class="ltx_td">Baseline</td><td class="ltx_td">5.0</td></tr><tr class="ltx_tr"><td class="ltx_td">Ours</td><td class="ltx_td"><span class="ltx_font_bold">4.1</span></td></tr></tbody></table></div></figure>
<section class="ltx_paragraph"><h4 class="ltx_title ltx_title_paragraph">Limitations.</h4>
<p class="ltx_p">The model struggles with heavily accented speech and very noisy rooms.</p></section>
</section>
<section id="S6" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag">6 </span>Conclusion</h2>
<div class="ltx_para"><p class="ltx_p">We showed that small speech models can run on phones with a <math alttext="3.2\\times" display="inline"><mn>3.2</mn></math> speed-up.</p></div></section>
<section id="Sx1" class="ltx_section"><h2 class="ltx_title ltx_title_section">Acknowledgements</h2><p>We thank our funders.</p></section>
<section id="bib" class="ltx_bibliography"><h2>References</h2><ul><li>Cited, 2020.</li></ul></section>
<section id="A1" class="ltx_appendix"><h2 class="ltx_title ltx_title_appendix">Appendix A More results</h2>
<figure class="ltx_table"><table><tr><td>x</td><td>y</td></tr><tr><td>1</td><td>2</td></tr></table></figure></section>
</article></body></html>`;

test("breakdown copies the paper's own parts", () => {
  const b = parseBreakdown(PAGE);
  assert.deepEqual(b.outline, ["Introduction", "Experiments", "Conclusion"]);
  assert.deepEqual(b.contributions, ["We cut memory use by 48% with a distillation loss.", "We release code at https://github.com/ana/tiny-speech."]);
  assert.equal(b.tables.length, 1); // the appendix table is left out
  assert.equal(b.tables[0].caption, "Table 1: Word error rate on LibriSpeech.");
  assert.deepEqual(b.tables[0].rows, [["Model", "WER"], ["Baseline", "5.0"], ["Ours", "4.1"]]);
  assert.equal(b.limitations?.heading, "Limitations");
  assert.match(b.limitations!.text, /accented speech/);
  assert.equal(b.conclusion?.heading, "Conclusion");
  assert.match(b.conclusion!.text, /3\.2× speed-up/);
  assert.deepEqual(b.links, ["https://github.com/ana/tiny-speech"]);
  assert.ok(worthShowing(b));
});

test("contributions fall back to the introduction's claim sentences", () => {
  const page = `<section class="ltx_section"><h2>1 Introduction</h2><p>Phones are slow. In this paper we propose a smaller speech model that runs offline. It is good.</p></section>
<section class="ltx_section"><h2>2 Method</h2><p>Text.</p></section><section class="ltx_section"><h2>3 Results</h2><p>Text.</p></section>`;
  assert.deepEqual(parseBreakdown(page).contributions, ["In this paper we propose a smaller speech model that runs offline."]);
});

test("limitations can be a bold lead-in paragraph", () => {
  const page = `<section class="ltx_section"><h2>5 Discussion</h2><p class="ltx_p"><span class="ltx_text ltx_font_bold">Limitations.</span> Our study covers only English and three model sizes, so results may not transfer.</p></section>`;
  assert.match(parseBreakdown(page).limitations!.text, /^Our study covers only English/);
});

test("an empty or failed page is not worth showing", () => {
  assert.equal(worthShowing(parseBreakdown("<html><body>Conversion failed</body></html>")), false);
});

test("text helpers tidy LaTeX, citations and numbering", () => {
  assert.equal(tidyTex("38.6\\times"), "38.6×");
  assert.equal(tidyTex("\\mathrm{FPS}\\approx 9"), "FPS≈ 9");
  assert.equal(textOf('Fast <cite class="ltx_cite">[3]</cite>.'), "Fast.");
  assert.equal(cleanHeading("6 Conclusion and Future Work"), "Conclusion and Future Work");
  assert.equal(cleanHeading("Appendix A More results"), "More results");
  assert.equal(cleanHeading("A Simple Baseline"), "A Simple Baseline");
  assert.equal(cleanHeading("4.2 Setup"), "Setup");
  assert.equal(cleanHeading("A.1 Details"), "Details");
});

test("summary keeps only sentences whose numbers are in the paper", () => {
  const source = "Speed-up of 3.2 times. Memory cut by 48%.";
  const raw = JSON.stringify({ summary: "It runs speech models on phones. It is 3.2 times faster. It cuts memory by 60%. Phone app makers would use it." });
  assert.equal(parseSummary(raw, source), "It runs speech models on phones. It is 3.2 times faster. Phone app makers would use it.");
  assert.equal(parseSummary("not json", source), null);
  assert.deepEqual(numbersIn("9 FPS, 38.6x and 48%"), ["9", "38.6", "48"]);
});

test("summary input stays small", () => {
  const b = parseBreakdown(PAGE);
  const input = summaryInput("Tiny Speech", "x".repeat(10000), b);
  assert.ok(input.length <= 6000);
  assert.match(summaryInput("Tiny Speech", "We distil.", b), /Contributions:\n- We cut memory/);
});

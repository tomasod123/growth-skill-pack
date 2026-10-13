# Subagent prompt: vision-tag ad structures (~20 images each)

Read each image in this list ONE AT A TIME with the Read tool (never several in one call; every image must be under 2000 px):
[list of {id, img}]
For each, output:
{"id", "layout" (e.g. photo-with-headline, type-only, screenshot, split, list, quote-card, meme, before-after),
 "hook_type" (question, statement, number, contrarian, callout, testimonial, offer),
 "icp_callout_text" (the words that name the audience, or null), "headline_on_image",
 "text_lines" (count of separate text elements on the image, including CTA buttons and logos with words),
 "text_density" (low/medium/high), "style", "colours", "person" (none/founder/customer/staff/stock),
 "proof_element", "cta_on_image", "transferable_structure" (one sentence a designer could build from)}
Write to `work/tags_[NN].json`. If an image will not load, output the id with layout null.

/* The banner is the only thing on this page that is not static copy, and it
   exists so nobody walks into the demo with the merchant services down. */

(async () => {
  const banner = document.getElementById("banner");
  const stat = document.getElementById("herostat");
  try {
    const s = await (await fetch("/api/scenario")).json();
    banner.innerHTML =
      `${s.merchants.length} merchant services live · ` +
      (s.live_transport
        ? `<span class="ok">transport ${s.live_transport}</span>`
        : `<span class="warn">no live transport — the chat will not answer</span>`);
    // Derived in /api/scenario from the same ledger the demo uses. A dollar
    // figure typed into this file would be the one number on the site nobody
    // could trace to a function.
    const st = s.stranded;
    const withheld = st.benefits_published - st.benefits_delivered;
    stat.innerHTML =
      `In this scenario the merchant publishes <b>${st.benefits_published}</b> benefits ` +
      `worth <b>$${st.recoverable_aud.toFixed(2)}</b> of signed, verifiable value — ` +
      `and an agent that cannot negotiate the extension receives ` +
      `<b>${withheld === st.benefits_published ? "none of it" : withheld + " fewer"}</b>.`;
  } catch (err) {
    banner.innerHTML = `<span class="warn">the demo server is not answering</span>`;
  }
})();

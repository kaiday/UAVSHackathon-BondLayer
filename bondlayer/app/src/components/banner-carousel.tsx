"use client";

import Image from "next/image";
import { useState, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import styles from "./banner-carousel.module.css";

/**
 * Promotional banners at the top of the overview. `main.jpeg` is always the
 * first slide on every visit; the rest follow in a fixed order. Files live in
 * public/banners (copied from data/banner) and are served under /console.
 */
const BANNERS = [
  { file: "main.jpeg", alt: "BondLayer connects a retail store to AI shopping agents" },
  { file: "old.jpeg", alt: "Example retailer promotions: clearance, flash sale and members' savings banners" },
  { file: "store.jpeg", alt: "Example in-store promotion: a supermarket spring savings banner" },
  { file: "tech.jpeg", alt: "Example local promotion: a neighbourhood market spring savings banner" },
];

const INTERVAL_MS = 5000;

export function BannerCarousel() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const count = BANNERS.length;

  // Restarting the timer whenever the slide changes means a manual click also
  // gets a full five seconds before the next automatic change.
  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(() => setIndex((i) => (i + 1) % count), INTERVAL_MS);
    return () => window.clearTimeout(timer);
  }, [index, paused, count]);

  const go = (next: number) => setIndex((next + count) % count);

  return (
    <section
      className={styles.carousel}
      aria-roledescription="carousel"
      aria-label="BondLayer highlights"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div className={styles.track}>
        {BANNERS.map((banner, i) => (
          <div
            key={banner.file}
            className={`${styles.slide} ${i === index ? styles.active : ""}`}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${count}`}
            aria-hidden={i !== index}
          >
            <Image
              className={styles.image}
              src={`/console/banners/${banner.file}`}
              alt={banner.alt}
              fill
              sizes="(max-width: 760px) 100vw, 1200px"
              priority={i === 0}
            />
          </div>
        ))}
      </div>

      <button type="button" className={`${styles.nav} ${styles.prev}`} onClick={() => go(index - 1)} aria-label="Previous banner">
        <ChevronLeft size={18} strokeWidth={2.4} aria-hidden="true" />
      </button>
      <button type="button" className={`${styles.nav} ${styles.next}`} onClick={() => go(index + 1)} aria-label="Next banner">
        <ChevronRight size={18} strokeWidth={2.4} aria-hidden="true" />
      </button>

      <div className={styles.dots}>
        {BANNERS.map((banner, i) => (
          <button
            key={banner.file}
            type="button"
            className={styles.dot}
            onClick={() => go(i)}
            aria-label={`Show banner ${i + 1} of ${count}`}
            aria-current={i === index}
          />
        ))}
      </div>
    </section>
  );
}

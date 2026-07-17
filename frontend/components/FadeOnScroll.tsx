"use client";

import { useEffect, useRef, useState } from "react";

// Fades its children out while the page is scrolling and back in when it
// settles — keeps the sidebar out of the way of the content sweep. Only
// applies on lg+ (where it's actually a sidebar); stacked mobile layout is
// unaffected.
export default function FadeOnScroll({ children }: { children: React.ReactNode }) {
  const [scrolling, setScrolling] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const onScroll = () => {
      setScrolling(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setScrolling(false), 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      clearTimeout(timer.current);
    };
  }, []);

  return (
    <div
      className={`transition-opacity duration-500 ease-out ${
        scrolling ? "lg:pointer-events-none lg:opacity-0" : "opacity-100"
      }`}
    >
      {children}
    </div>
  );
}

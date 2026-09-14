import { useRef } from "react";
import { LOGO_URL } from "../theme.js";
import { MotionProvider } from "./home/MotionContext.jsx";
import SmoothScroll from "./home/SmoothScroll.jsx";
import ScrollTint from "./home/ScrollTint.jsx";
import Hero from "./home/Hero.jsx";
import ProblemSection from "./home/ProblemSection.jsx";
import InsightSection from "./home/InsightSection.jsx";
import ProductRevealSection from "./home/ProductRevealSection.jsx";
import MetricsSection from "./home/MetricsSection.jsx";
import HowItWorksSection from "./home/HowItWorksSection.jsx";
import DifferentiationSection from "./home/DifferentiationSection.jsx";
import ImpactNetworkSection from "./home/ImpactNetworkSection.jsx";
import FinalCtaSection from "./home/FinalCtaSection.jsx";

/**
 * SENTINEL's first impression, shown by LoginGate before authentication.
 * Presentational only — auth state and the submit handler live in
 * LoginGate and are passed straight through to FinalCtaSection, so the
 * login flow itself is untouched.
 *
 * Every scroll section tells one beat of the same story: one ordinary feed
 * -> thousands of disconnected feeds -> the correlation insight -> the real
 * product -> how it works -> why it's different -> the scale it's built
 * for -> sign in. See DEVELOPER_README / this PR's description for the
 * full storyboard.
 */
export default function LandingPage({
  username,
  setUsername,
  password,
  setPassword,
  error,
  busy,
  onSubmit,
}) {
  const ctaRef = useRef(null);

  const scrollToSignIn = () => {
    ctaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <MotionProvider>
      <SmoothScroll>
        <div className="hp-root">
          <ScrollTint />
          <header className="ld-nav">
            <div className="ld-nav-brand">
              <img
                src={LOGO_URL}
                alt=""
                className="ld-nav-logo"
                onError={(e) => (e.currentTarget.style.display = "none")}
              />
              <span>SENTINEL</span>
            </div>
            <button className="ld-nav-cta" onClick={scrollToSignIn}>
              Sign in
            </button>
          </header>

          <Hero onEnter={scrollToSignIn} />
          <ProblemSection />
          <InsightSection />
          <ProductRevealSection />
          <MetricsSection />
          <HowItWorksSection />
          <DifferentiationSection />
          <ImpactNetworkSection />
          <FinalCtaSection
            ref={ctaRef}
            username={username}
            setUsername={setUsername}
            password={password}
            setPassword={setPassword}
            error={error}
            busy={busy}
            onSubmit={onSubmit}
          />

          <footer className="ld-footer">SENTINEL — Gujarat Police CCTV Integration Platform</footer>
        </div>
      </SmoothScroll>
    </MotionProvider>
  );
}

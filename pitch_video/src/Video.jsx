import { Series, AbsoluteFill } from "remotion";
import { Scene1Problem } from "./scenes/Scene1Problem.jsx";
import { Scene2ProblemDetail } from "./scenes/Scene2ProblemDetail.jsx";
import { Scene3Reveal } from "./scenes/Scene3Reveal.jsx";
import { Scene4Journey } from "./scenes/Scene4Journey.jsx";
import { Scene5Workflow } from "./scenes/Scene5Workflow.jsx";
import { Scene6Proof } from "./scenes/Scene6Proof.jsx";
import { Scene7Landing } from "./scenes/Scene7Landing.jsx";
import { Scene8Close } from "./scenes/Scene8Close.jsx";
import { theme } from "./theme.js";

// Frame budget @ 30fps — mirrors PITCH_VIDEO_SCRIPT.md exactly (sums to
// 2250 frames = 75s). Change a duration here AND in the script together.
export const DURATIONS = {
  problem: 240, // 0:00–0:08
  detail: 300, // 0:08–0:18
  reveal: 420, // 0:18–0:32
  journey: 540, // 0:32–0:50  (HERO)
  workflow: 300, // 0:50–1:00
  proof: 210, // 1:00–1:07
  landing: 90, // 1:07–1:10
  close: 150, // 1:10–1:15
};

export const TOTAL_DURATION = Object.values(DURATIONS).reduce((a, b) => a + b, 0);

export const Video = () => (
  <AbsoluteFill style={{ backgroundColor: theme.bg, fontFamily: theme.fontSans }}>
    <Series>
      <Series.Sequence durationInFrames={DURATIONS.problem}>
        <Scene1Problem durationInFrames={DURATIONS.problem} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.detail}>
        <Scene2ProblemDetail durationInFrames={DURATIONS.detail} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.reveal}>
        <Scene3Reveal durationInFrames={DURATIONS.reveal} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.journey}>
        <Scene4Journey durationInFrames={DURATIONS.journey} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.workflow}>
        <Scene5Workflow durationInFrames={DURATIONS.workflow} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.proof}>
        <Scene6Proof durationInFrames={DURATIONS.proof} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.landing}>
        <Scene7Landing durationInFrames={DURATIONS.landing} />
      </Series.Sequence>
      <Series.Sequence durationInFrames={DURATIONS.close}>
        <Scene8Close durationInFrames={DURATIONS.close} />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);

import { Composition } from "remotion";
import { Video, TOTAL_DURATION } from "./Video.jsx";

export const RemotionRoot = () => (
  <Composition
    id="Sentinel"
    component={Video}
    durationInFrames={TOTAL_DURATION}
    fps={30}
    width={1920}
    height={1080}
  />
);

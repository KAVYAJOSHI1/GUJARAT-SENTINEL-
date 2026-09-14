import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadDMMono } from "@remotion/google-fonts/DMMono";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";

// Side-effect calls: each injects the stylesheet + blocks rendering until
// loaded (Remotion's delayRender under the hood) — must run before the root
// registers any composition.
loadAnton("normal");
loadDMMono("normal");
loadInter("normal", { weights: ["400", "500", "600"] });

import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root.jsx";

registerRoot(RemotionRoot);

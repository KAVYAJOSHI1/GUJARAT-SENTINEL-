import { useEffect, useRef } from "react";
import * as THREE from "three";
import { useReducedMotion } from "./MotionContext.jsx";

const ACCENT = 0x5ecfb8;
const ACCENT_LIGHT = 0x8ee4d0;
const RIM_WARM = 0xe85d4a;

/**
 * The Home page's 3D centerpiece — a procedurally-built scanning aperture,
 * not a loaded .glb. This mirrors how the Orqis reference site actually
 * builds its own centerpiece (raw three.js primitives — BufferGeometry /
 * TorusGeometry / Points — no GLTFLoader in its bundle at all), just themed
 * as an aperture/eye instead of their robot mascot: SENTINEL is a vision
 * system, not an agent character, so the motif changes but the visual
 * language (glossy dark core, coloured rim light, ambient particles,
 * mouse-follow + scroll-reactive) carries over directly.
 */
export default function ThreeScene({ className }) {
  const mountRef = useRef(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 6.2);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    // ── the aperture core ────────────────────────────────────────────────
    const group = new THREE.Group();
    scene.add(group);

    const core = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.85, 2),
      new THREE.MeshPhysicalMaterial({
        color: 0x0a0f0d,
        metalness: 0.75,
        roughness: 0.22,
        clearcoat: 0.6,
        clearcoatRoughness: 0.25,
      })
    );
    group.add(core);

    const wire = new THREE.Mesh(
      new THREE.IcosahedronGeometry(0.87, 1),
      new THREE.MeshBasicMaterial({ color: ACCENT, wireframe: true, transparent: true, opacity: 0.5 })
    );
    group.add(wire);

    const ringGeo = new THREE.TorusGeometry(1.5, 0.012, 12, 128);
    const ringA = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: ACCENT_LIGHT, transparent: true, opacity: 0.65 }));
    ringA.rotation.x = Math.PI / 2.3;
    group.add(ringA);

    const ringB = new THREE.Mesh(
      new THREE.TorusGeometry(1.85, 0.008, 12, 128),
      new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.3 })
    );
    ringB.rotation.x = Math.PI / 1.8;
    ringB.rotation.y = 0.4;
    group.add(ringB);

    // Ambient camera-network particles orbiting the core.
    const particleCount = 90;
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      const r = 2.3 + Math.random() * 1.6;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.6;
      positions[i * 3 + 2] = r * Math.cos(phi);
    }
    const particleGeo = new THREE.BufferGeometry();
    particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const particles = new THREE.Points(
      particleGeo,
      new THREE.PointsMaterial({ color: ACCENT_LIGHT, size: 0.035, transparent: true, opacity: 0.55 })
    );
    scene.add(particles);

    // ── lighting: warm rim + accent fill, matching the reference's coloured
    //    rim-light-on-glossy-dark-plastic treatment ──────────────────────
    scene.add(new THREE.AmbientLight(0x203028, 1.1));
    const rim = new THREE.PointLight(RIM_WARM, 12, 20);
    rim.position.set(-3, 1.5, -2);
    scene.add(rim);
    const fill = new THREE.PointLight(ACCENT, 14, 20);
    fill.position.set(2.5, -1, 3);
    scene.add(fill);
    const front = new THREE.PointLight(0xffffff, 3, 20);
    front.position.set(0, 2, 4);
    scene.add(front);

    // ── sizing ───────────────────────────────────────────────────────────
    function resize() {
      const { clientWidth: w, clientHeight: h } = mount;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    // ── mouse-follow: the aperture "looks" toward the cursor ────────────
    const pointer = { x: 0, y: 0 };
    function onPointerMove(e) {
      pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
    }
    if (!reduced) window.addEventListener("pointermove", onPointerMove);

    // Scroll parallax for the whole centerpiece (position/opacity/scale) is
    // handled by the parent (Hero.jsx) tweening the DOM wrapper directly —
    // keeping that in one place instead of also fighting it here from
    // inside the render loop, which read as the object "breaking" rather
    // than receding.
    let raf;
    const clock = new THREE.Clock();
    function tick() {
      const dt = clock.getDelta();
      const idle = reduced ? 0 : dt;

      group.rotation.y += idle * 0.18;
      wire.rotation.y -= idle * 0.12;
      ringA.rotation.z += idle * 0.25;
      ringB.rotation.z -= idle * 0.15;
      particles.rotation.y += idle * 0.05;

      if (!reduced) {
        group.rotation.x = THREE.MathUtils.lerp(group.rotation.x, pointer.y * 0.25, 0.04);
        group.rotation.y += (pointer.x * 0.35 - (group.rotation.y % (Math.PI * 2))) * 0.0006;
      }

      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    }
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onPointerMove);
      mount.removeChild(renderer.domElement);
      [core, wire, ringA, ringB, particles].forEach((m) => {
        m.geometry?.dispose();
        m.material?.dispose();
      });
      renderer.dispose();
    };
  }, [reduced]);

  return <div ref={mountRef} className={className} aria-hidden="true" />;
}

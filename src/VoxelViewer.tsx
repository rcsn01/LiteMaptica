import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { blockColor, confidenceColor } from "./palette";
import type { VoxelProposal } from "./types";

interface Props {
  voxels: VoxelProposal[];
  confidenceMode: boolean;
  selected: VoxelProposal | null;
  onSelect: (voxel: VoxelProposal | null) => void;
}

export function VoxelViewer({ voxels, confidenceMode, selected, onSelect }: Props) {
  const mount = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mount.current) return;
    const host = mount.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0f0d);
    scene.fog = new THREE.FogExp2(0x0a0f0d, 0.016);
    const camera = new THREE.PerspectiveCamera(48, host.clientWidth / host.clientHeight, 0.1, 1000);
    camera.position.set(14, 11, 16);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.target.set(0, 2, 0);
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = 4;
    controls.maxDistance = 90;

    scene.add(new THREE.HemisphereLight(0xd8f5e5, 0x16241c, 2.2));
    const sun = new THREE.DirectionalLight(0xfff2d1, 2.8);
    sun.position.set(8, 15, 10);
    sun.castShadow = true;
    scene.add(sun);

    const grid = new THREE.GridHelper(64, 64, 0x324a3e, 0x18251f);
    grid.position.y = -0.51;
    scene.add(grid);

    const geometry = new THREE.BoxGeometry(0.97, 0.97, 0.97);
    const material = new THREE.MeshStandardMaterial({ roughness: 0.86, metalness: 0.02, vertexColors: true });
    const instances = new THREE.InstancedMesh(geometry, material, Math.max(1, voxels.length));
    instances.castShadow = true;
    instances.receiveShadow = true;
    const matrix = new THREE.Matrix4();
    voxels.forEach((voxel, index) => {
      matrix.makeTranslation(...voxel.position);
      instances.setMatrixAt(index, matrix);
      instances.setColorAt(index, new THREE.Color(confidenceMode ? confidenceColor(voxel.occupancyConfidence, voxel.materialConfidence) : blockColor(voxel.state)));
    });
    instances.count = voxels.length;
    scene.add(instances);

    const selection = new THREE.Box3Helper(new THREE.Box3(), new THREE.Color(0xe5ba72));
    selection.visible = false;
    scene.add(selection);
    if (selected) {
      const [x, y, z] = selected.position;
      selection.box.set(new THREE.Vector3(x - 0.51, y - 0.51, z - 0.51), new THREE.Vector3(x + 0.51, y + 0.51, z + 0.51));
      selection.visible = true;
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const click = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const match = raycaster.intersectObject(instances)[0];
      onSelect(match?.instanceId === undefined ? null : voxels[match.instanceId]);
    };
    renderer.domElement.addEventListener("click", click);

    const resize = () => {
      camera.aspect = host.clientWidth / host.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(host.clientWidth, host.clientHeight);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    let animation = 0;
    const render = () => { controls.update(); renderer.render(scene, camera); animation = requestAnimationFrame(render); };
    render();
    return () => {
      cancelAnimationFrame(animation);
      observer.disconnect();
      renderer.domElement.removeEventListener("click", click);
      controls.dispose(); geometry.dispose(); material.dispose(); renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, [voxels, confidenceMode, selected, onSelect]);

  return <div className="viewer" ref={mount}><div className="viewer-hint">Drag to orbit · scroll to zoom · click to inspect</div></div>;
}

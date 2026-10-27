import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { decodeHeights, type Overlay, type Terrain } from '../api'

export type QuakePoint = { x: number; y: number; depth: number; mag: number; ageH: number }
export type Label = { x: number; y: number; text: string; kind?: 'place' | 'vent' | 'zonelabel' }
export type SurfacePoint = { x: number; y: number; v: number }

type Props = {
  terrain: Terrain | null
  overlay?: Overlay | null
  quakes?: QuakePoint[]
  labels?: Label[]
  exaggeration?: number
  depthScale?: number
  terrainOpacity?: number
  maxDepthKm?: number
  focus?: { x: number; y: number; distKm: number } | null
  quakeScale?: number
  surfacePoints?: SurfacePoint[]
}

const km = 1000

export default function Atlas3D({ terrain, overlay, quakes = [], labels = [], exaggeration = 1.6, depthScale = 0.5,
  terrainOpacity = 0.86, maxDepthKm = 40, focus, quakeScale = 1, surfacePoints = [] }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const S = useRef<any>({})

  // ---------- scene setup (once)
  useEffect(() => {
    const el = host.current!
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    el.appendChild(renderer.domElement)
    const labelsR = new CSS2DRenderer()
    labelsR.domElement.className = 'labels-layer'
    el.appendChild(labelsR.domElement)
    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog(0xe9e3d6, 60, 260)
    const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 2000)
    camera.position.set(-18, 16, 26)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.maxPolarAngle = Math.PI * 0.62
    scene.add(new THREE.AmbientLight(0xffffff, 1))
    const groups = { terrain: new THREE.Group(), quakes: new THREE.Group(), labels: new THREE.Group(), guides: new THREE.Group(), points: new THREE.Group() }
    Object.values(groups).forEach((g) => scene.add(g))
    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight
      renderer.setSize(w, h)
      labelsR.setSize(w, h)
      camera.aspect = w / Math.max(h, 1)
      camera.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    resize()
    let raf = 0
    const loop = () => {
      controls.update()
      renderer.render(scene, camera)
      labelsR.render(scene, camera)
      raf = requestAnimationFrame(loop)
    }
    loop()
    S.current = { renderer, scene, camera, controls, groups, labelsR }
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls.dispose()
      renderer.dispose()
      el.innerHTML = ''
    }
  }, [])

  // ---------- terrain + overlay texture
  useEffect(() => {
    const s = S.current
    if (!terrain || !s.scene) return
    const g: THREE.Group = s.groups.terrain
    g.clear()
    const { rows, cols, step } = terrain
    const cx = terrain.west + (cols * step) / 2, cy = terrain.north - (rows * step) / 2
    s.center = { cx, cy }
    const h = decodeHeights(terrain)
    const pos = new Float32Array(rows * cols * 3)
    const uv = new Float32Array(rows * cols * 2)
    for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
      const k = i * cols + j
      const x = terrain.west + (j + 0.5) * step, y = terrain.north - (i + 0.5) * step
      const z = h[k]
      pos[3 * k] = (x - cx) / km
      pos[3 * k + 1] = Number.isNaN(z) ? -0.03 : (z / km) * exaggeration
      pos[3 * k + 2] = -(y - cy) / km
      uv[2 * k] = (j + 0.5) / cols
      uv[2 * k + 1] = 1 - (i + 0.5) / rows
    }
    const idx: number[] = []
    for (let i = 0; i < rows - 1; i++) for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j, b = a + 1, c = a + cols, d = c + 1
      if (Number.isNaN(h[a]) && Number.isNaN(h[b]) && Number.isNaN(h[c]) && Number.isNaN(h[d])) continue
      idx.push(a, c, b, b, c, d)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
    geo.setIndex(idx)
    geo.computeVertexNormals()
    const canvas = document.createElement('canvas')
    const tex = new THREE.CanvasTexture(canvas)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = 8
    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: terrainOpacity, side: THREE.DoubleSide, depthWrite: true })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.renderOrder = 2
    g.add(mesh)
    // sea plane
    const sea = new THREE.Mesh(new THREE.PlaneGeometry(600, 600), new THREE.MeshBasicMaterial({ color: 0xd6dbdd, transparent: true, opacity: 0.55, depthWrite: false }))
    sea.rotation.x = -Math.PI / 2
    sea.position.y = -0.04
    g.add(sea)
    s.terrainMesh = mesh
    s.texCanvas = canvas
    s.tex = tex
    s.terrainMeta = terrain
    const base = new Image()
    base.onload = () => { s.baseImg = base; composeTexture() }
    base.src = terrain.texture
    // initial camera framing
    const span = Math.max(rows, cols) * step / km
    s.camera.position.set(-span * 0.55, span * 0.55, span * 0.75)
    s.controls.target.set(0, 0, 0)
    s.controls.maxDistance = span * 3
    s.scene.fog = new THREE.Fog(0xe9e3d6, span * 1.4, span * 4.5)
    // depth guides
    const gd: THREE.Group = s.groups.guides
    gd.clear()
    for (const d of [10, 20, 30, 40].filter((d) => d <= maxDepthKm)) {
      const yy = -d * depthScale
      const ring = new THREE.LineLoop(
        new THREE.BufferGeometry().setFromPoints([[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => new THREE.Vector3(a * cols * step / km / 2, yy, b * rows * step / km / 2))),
        new THREE.LineBasicMaterial({ color: 0x9c9284, transparent: true, opacity: 0.45 }))
      gd.add(ring)
      const div = document.createElement('div')
      div.className = 'depth-tick'
      div.textContent = `${d} km`
      const lab = new CSS2DObject(div)
      lab.position.set(-cols * step / km / 2, yy, rows * step / km / 2)
      gd.add(lab)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [terrain, exaggeration, depthScale, maxDepthKm])

  const composeTexture = () => {
    const s = S.current
    if (!s.baseImg || !s.texCanvas) return
    const c: HTMLCanvasElement = s.texCanvas
    if (c.width !== s.baseImg.width || c.height !== s.baseImg.height) {
      // WebGL2 textures are immutable in size: on resize we create a new one
      c.width = s.baseImg.width
      c.height = s.baseImg.height
      const nt = new THREE.CanvasTexture(c)
      nt.colorSpace = THREE.SRGBColorSpace
      nt.anisotropy = 8
      s.tex?.dispose()
      s.tex = nt
      if (s.terrainMesh) { s.terrainMesh.material.map = nt; s.terrainMesh.material.needsUpdate = true }
    }
    const ctx = c.getContext('2d')!
    ctx.drawImage(s.baseImg, 0, 0)
    const t: Terrain = s.terrainMeta
    const k = c.width / t.cols
    if (s.overlayImg && s.overlayMeta) {
      const o: Overlay = s.overlayMeta
      const px = ((o.west - t.west) / t.step) * k
      const py = ((t.north - o.north) / t.step) * k
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(s.overlayImg, px, py, (o.cols * o.step / t.step) * k, (o.rows * o.step / t.step) * k)
    }
    s.tex.needsUpdate = true
  }

  useEffect(() => {
    const s = S.current
    if (!overlay) { s.overlayImg = null; s.overlayMeta = null; composeTexture(); return }
    const img = new Image()
    img.onload = () => { s.overlayImg = img; s.overlayMeta = overlay; composeTexture() }
    img.src = overlay.png
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlay])

  useEffect(() => {
    const s = S.current
    if (s.terrainMesh) s.terrainMesh.material.opacity = terrainOpacity
  }, [terrainOpacity])

  // ---------- quakes
  useEffect(() => {
    const s = S.current
    if (!s.scene || !s.center) return
    const g: THREE.Group = s.groups.quakes
    g.clear()
    if (!quakes.length) return
    const geo = new THREE.SphereGeometry(1, 14, 10)
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.92, depthWrite: false })
    const inst = new THREE.InstancedMesh(geo, mat, quakes.length)
    const m = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion()
    const hot = new THREE.Color('#e23d14'), warm = new THREE.Color('#f08a35'), old = new THREE.Color('#8f8577')
    quakes.forEach((e, i) => {
      const r = (0.05 + 0.055 * Math.max(0, e.mag)) * quakeScale
      m.compose(new THREE.Vector3((e.x - s.center.cx) / km, -e.depth * depthScale, -(e.y - s.center.cy) / km), q, new THREE.Vector3(r, r, r))
      inst.setMatrixAt(i, m)
      if (e.ageH <= 24) col.copy(hot)
      else if (e.ageH <= 24 * 7) col.copy(warm).lerp(old, (e.ageH - 24) / (24 * 6) * 0.5)
      else col.copy(old)
      inst.setColorAt(i, col)
    })
    inst.renderOrder = 1
    g.add(inst)
  }, [quakes, depthScale, terrain, quakeScale])

  // ---------- labels
  useEffect(() => {
    const s = S.current
    if (!s.scene || !s.center || !s.terrainMeta) return
    const g: THREE.Group = s.groups.labels
    g.clear()
    const t: Terrain = s.terrainMeta
    const h = s.heights ?? (s.heights = decodeHeights(t))
    labels.forEach((l) => {
      const j = Math.floor((l.x - t.west) / t.step), i = Math.floor((t.north - l.y) / t.step)
      const z = i >= 0 && i < t.rows && j >= 0 && j < t.cols ? h[i * t.cols + j] : 0
      const div = document.createElement('div')
      div.className = `map-label ${l.kind ?? 'place'}`
      div.textContent = l.text
      const o = new CSS2DObject(div)
      o.position.set((l.x - s.center.cx) / km, ((Number.isNaN(z) ? 0 : z) / km) * exaggeration + 0.15, -(l.y - s.center.cy) / km)
      g.add(o)
    })
  }, [labels, terrain, exaggeration])

  useEffect(() => { S.current.heights = null }, [terrain])

  // ---------- assets on the surface (e.g. buildings at risk), coloured by probability
  useEffect(() => {
    const s = S.current
    if (!s.scene || !s.center || !s.terrainMeta) return
    const g: THREE.Group = s.groups.points
    g.clear()
    if (!surfacePoints.length) return
    const t: Terrain = s.terrainMeta
    const h = s.heights ?? (s.heights = decodeHeights(t))
    const geo = new THREE.BoxGeometry(0.05, 0.05, 0.05)
    const mat = new THREE.MeshBasicMaterial({ depthTest: true })
    const inst = new THREE.InstancedMesh(geo, mat, surfacePoints.length)
    const m = new THREE.Matrix4(), col = new THREE.Color()
    const lo = new THREE.Color('#f2c14e'), hi = new THREE.Color('#7a0f0a'), pocket = new THREE.Color('#3f5fb0')
    surfacePoints.forEach((p, i) => {
      const j = Math.floor((p.x - t.west) / t.step), k = Math.floor((t.north - p.y) / t.step)
      const z = k >= 0 && k < t.rows && j >= 0 && j < t.cols ? h[k * t.cols + j] : 0
      m.makeTranslation((p.x - s.center.cx) / km, ((Number.isNaN(z) ? 0 : z) / km) * exaggeration + 0.02, -(p.y - s.center.cy) / km)
      inst.setMatrixAt(i, m)
      inst.setColorAt(i, p.v < 0 ? col.copy(pocket) : col.copy(lo).lerp(hi, Math.min(1, Math.max(0, p.v))))
    })
    inst.renderOrder = 3
    g.add(inst)
  }, [surfacePoints, terrain, exaggeration])

  // ---------- focus (fly to)
  useEffect(() => {
    const s = S.current
    if (!focus || !s.center) return
    const tx = (focus.x - s.center.cx) / km, tz = -(focus.y - s.center.cy) / km
    const d = focus.distKm
    const from = s.camera.position.clone(), fromT = s.controls.target.clone()
    const to = new THREE.Vector3(tx - d * 0.55, d * 0.6, tz + d * 0.7), toT = new THREE.Vector3(tx, 0, tz)
    let k = 0
    const anim = () => {
      k = Math.min(1, k + 0.035)
      const e = k * k * (3 - 2 * k)
      s.camera.position.lerpVectors(from, to, e)
      s.controls.target.lerpVectors(fromT, toT, e)
      if (k < 1) requestAnimationFrame(anim)
    }
    anim()
  }, [focus])

  return <div className="atlas3d" ref={host} />
}

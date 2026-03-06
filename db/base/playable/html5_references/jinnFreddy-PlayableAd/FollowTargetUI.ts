import { _decorator, Component, Node, Camera, Vec3, UITransform, Canvas } from 'cc';
const { ccclass, property } = _decorator;

@ccclass('FollowTargetUI')
export class FollowTargetUI extends Component {
    @property(Node) target3D: Node = null;   // 3D target to follow
    @property(Camera) mainCamera: Camera = null; // Main scene camera
    @property(Vec3) offset: Vec3 = new Vec3(0, 200, 0); // Screen-space offset

    private _uiTransform: UITransform = null;
    private _canvas: Canvas = null;

    /** Cache UI transform and canvas references */
    onLoad() {
        this._uiTransform = this.getComponent(UITransform);
        this._canvas = this.node.scene.getComponentInChildren(Canvas);
    }

    /** Position UI in screen space above 3D target */
    update(deltaTime: number) {
        if (!this.target3D || !this.mainCamera || !this._canvas?.cameraComponent) return;

        // Convert 3D world position to screen space
        const worldPos = this.target3D.worldPosition.clone();
        const screenPos = this.mainCamera.worldToScreen(worldPos);
        
        // Convert screen space to UI world space
        const uiPos = new Vec3();
        this._canvas.cameraComponent.screenToWorld(screenPos, uiPos);
        this.node.setWorldPosition(uiPos.add(this.offset));
        
        // Hide UI if target is behind camera
        this.node.active = screenPos.z > 0;
    }
}
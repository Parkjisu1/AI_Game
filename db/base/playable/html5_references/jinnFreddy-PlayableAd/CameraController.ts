import { _decorator, Component, Node, Vec3 } from 'cc';
const { ccclass, property } = _decorator;

@ccclass('CameraController')
export class CameraController extends Component {
    @property({ type: Node }) target: Node | null = null; // Player node to follow
    @property distance = 12;    // Distance from player (isometric radius)
    @property height = 8;       // Height above player
    @property angle = 45;       // Orbit angle (45° = classic isometric)
    @property smoothSpeed = 10; // Higher = smoother following

    private _desiredPosition = new Vec3();
    private _lookAtPosition = new Vec3();

    /** Initialize camera; validate target assignment */
    start() {
        if (!this.target) {
            console.error("	CameraController: 'target' not assigned!");
        }
    }

    /** Smoothly follow player with isometric orbit positioning */
    lateUpdate(deltaTime: number) {
        if (!this.target) return;

        // Calculate orbit position around player
        const angleRad = this.angle * Math.PI / 180;
        this._desiredPosition.set(
            this.target.position.x + Math.sin(angleRad) * this.distance,
            this.target.position.y + this.height,
            this.target.position.z + Math.cos(angleRad) * this.distance
        );

        // Smooth interpolation to target position
        const currentPos = this.node.position;
        const lerpFactor = 1 - Math.pow(0.1, this.smoothSpeed * deltaTime);
        Vec3.lerp(this._desiredPosition, currentPos, this._desiredPosition, lerpFactor);
        this.node.setPosition(this._desiredPosition);

        // Look at player's chest level with proper up vector
        Vec3.set(this._lookAtPosition,
            this.target.position.x,
            this.target.position.y + 1.5,
            this.target.position.z
        );
        this.node.lookAt(this._lookAtPosition, Vec3.UNIT_Y);
    }
}
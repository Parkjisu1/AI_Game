import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import java.lang.reflect.Method;

public class FingerDrag {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: FingerDrag <x> <y> [dy_offset]");
            System.exit(1);
        }

        float x = Float.parseFloat(args[0]);
        float y = Float.parseFloat(args[1]);
        float dy = args.length > 2 ? Float.parseFloat(args[2]) : -100f;

        Class<?> imClass = Class.forName("android.hardware.input.InputManager");
        Method getInstance = imClass.getDeclaredMethod("getInstance");
        Object im = getInstance.invoke(null);
        Method inject = imClass.getDeclaredMethod("injectInputEvent",
            android.view.InputEvent.class, int.class);

        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[1];
        props[0] = new MotionEvent.PointerProperties();
        props[0].id = 0;
        props[0].toolType = MotionEvent.TOOL_TYPE_FINGER;

        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[1];
        coords[0] = new MotionEvent.PointerCoords();
        coords[0].pressure = 1.0f;
        coords[0].size = 1.0f;

        long downTime = SystemClock.uptimeMillis();

        // ACTION_DOWN at pig position
        coords[0].x = x;
        coords[0].y = y;
        MotionEvent down = MotionEvent.obtain(
            downTime, downTime, MotionEvent.ACTION_DOWN,
            1, props, coords, 0, 0, 1.0f, 1.0f,
            0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        inject.invoke(im, down, 2);
        down.recycle();

        // ACTION_MOVE - drag upward in steps
        int steps = 10;
        for (int i = 1; i <= steps; i++) {
            Thread.sleep(16);
            long t = SystemClock.uptimeMillis();
            coords[0].x = x;
            coords[0].y = y + (dy * i / steps);
            MotionEvent move = MotionEvent.obtain(
                downTime, t, MotionEvent.ACTION_MOVE,
                1, props, coords, 0, 0, 1.0f, 1.0f,
                0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
            inject.invoke(im, move, 2);
            move.recycle();
        }

        Thread.sleep(50);

        // ACTION_UP
        long upTime = SystemClock.uptimeMillis();
        coords[0].x = x;
        coords[0].y = y + dy;
        MotionEvent up = MotionEvent.obtain(
            downTime, upTime, MotionEvent.ACTION_UP,
            1, props, coords, 0, 0, 1.0f, 1.0f,
            0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        inject.invoke(im, up, 2);
        up.recycle();
    }
}

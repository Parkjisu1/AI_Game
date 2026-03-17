import android.os.SystemClock;
import android.view.InputDevice;
import android.view.MotionEvent;
import java.lang.reflect.Method;

public class FingerTap {
    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Usage: FingerTap <x> <y>");
            System.exit(1);
        }

        float x = Float.parseFloat(args[0]);
        float y = Float.parseFloat(args[1]);

        long downTime = SystemClock.uptimeMillis();

        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[1];
        props[0] = new MotionEvent.PointerProperties();
        props[0].id = 0;
        props[0].toolType = MotionEvent.TOOL_TYPE_FINGER;

        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[1];
        coords[0] = new MotionEvent.PointerCoords();
        coords[0].x = x;
        coords[0].y = y;
        coords[0].pressure = 1.0f;
        coords[0].size = 1.0f;

        MotionEvent down = MotionEvent.obtain(
            downTime, downTime, MotionEvent.ACTION_DOWN,
            1, props, coords,
            0, 0, 1.0f, 1.0f,
            0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0
        );

        // Use reflection for InputManager hidden API
        Class<?> imClass = Class.forName("android.hardware.input.InputManager");
        Method getInstance = imClass.getDeclaredMethod("getInstance");
        Object im = getInstance.invoke(null);
        Method inject = imClass.getDeclaredMethod("injectInputEvent",
            android.view.InputEvent.class, int.class);

        inject.invoke(im, down, 2);

        Thread.sleep(50);

        long upTime = SystemClock.uptimeMillis();
        MotionEvent up = MotionEvent.obtain(
            downTime, upTime, MotionEvent.ACTION_UP,
            1, props, coords,
            0, 0, 1.0f, 1.0f,
            0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0
        );

        inject.invoke(im, up, 2);

        down.recycle();
        up.recycle();
    }
}

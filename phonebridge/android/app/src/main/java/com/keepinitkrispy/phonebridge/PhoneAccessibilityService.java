package com.keepinitkrispy.phonebridge;

import android.accessibilityservice.AccessibilityService;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayDeque;

public class PhoneAccessibilityService extends AccessibilityService {
    private static volatile PhoneAccessibilityService instance;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        try {
            JSONObject o = new JSONObject();
            o.put("time", System.currentTimeMillis());
            if (event.getPackageName() != null) o.put("package", event.getPackageName().toString());
            if (event.getClassName() != null) o.put("class", event.getClassName().toString());
            AccessibilityNodeInfo root = getRootInActiveWindow();
            JSONArray text = new JSONArray();
            if (root != null) collectText(root, text, 120);
            o.put("visible_text", text);
            getSharedPreferences(BridgeCore.PREFS, MODE_PRIVATE).edit().putString("last_screen", o.toString()).apply();
        } catch (Exception ignored) {}
    }

    private void collectText(AccessibilityNodeInfo root, JSONArray out, int max) {
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<>();
        q.add(root);
        while (!q.isEmpty() && out.length() < max) {
            AccessibilityNodeInfo n = q.removeFirst();
            CharSequence t = n.getText();
            CharSequence d = n.getContentDescription();
            if (t != null && t.length() > 0) out.put(t.toString());
            else if (d != null && d.length() > 0) out.put(d.toString());
            for (int i = 0; i < n.getChildCount(); i++) {
                AccessibilityNodeInfo child = n.getChild(i);
                if (child != null) q.addLast(child);
            }
        }
    }

    public static boolean performBridgeAction(String action) {
        PhoneAccessibilityService s = instance;
        if (s == null) return false;
        if ("home".equals(action)) return s.performGlobalAction(GLOBAL_ACTION_HOME);
        if ("back".equals(action)) return s.performGlobalAction(GLOBAL_ACTION_BACK);
        return false;
    }

    @Override
    public void onInterrupt() {}

    @Override
    public void onDestroy() {
        if (instance == this) instance = null;
        super.onDestroy();
    }
}

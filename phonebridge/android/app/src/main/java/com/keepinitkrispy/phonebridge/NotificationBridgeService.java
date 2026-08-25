package com.keepinitkrispy.phonebridge;

import android.app.Notification;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

import org.json.JSONObject;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;

public class NotificationBridgeService extends NotificationListenerService {
    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            Notification n = sbn.getNotification();
            JSONObject o = new JSONObject();
            o.put("event", "posted");
            o.put("time", System.currentTimeMillis());
            o.put("package", sbn.getPackageName());
            o.put("key", sbn.getKey());
            o.put("ongoing", sbn.isOngoing());
            if (n.extras != null) {
                CharSequence title = n.extras.getCharSequence(Notification.EXTRA_TITLE);
                CharSequence text = n.extras.getCharSequence(Notification.EXTRA_TEXT);
                CharSequence big = n.extras.getCharSequence(Notification.EXTRA_BIG_TEXT);
                if (title != null) o.put("title", title.toString());
                if (text != null) o.put("text", text.toString());
                if (big != null && (text == null || !big.toString().equals(text.toString()))) o.put("big_text", big.toString());
            }
            appendTrim(o);
            BridgeCore.syncNow(this, "notification-posted");
        } catch (Exception ignored) {}
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
        try {
            JSONObject o = new JSONObject();
            o.put("event", "removed");
            o.put("time", System.currentTimeMillis());
            o.put("package", sbn.getPackageName());
            o.put("key", sbn.getKey());
            appendTrim(o);
        } catch (Exception ignored) {}
    }

    private synchronized void appendTrim(JSONObject o) {
        File f = new File(getFilesDir(), "notifications.jsonl");
        try (BufferedWriter w = new BufferedWriter(new FileWriter(f, true))) {
            w.write(o.toString());
            w.newLine();
        } catch (Exception ignored) {}
        if (f.length() > 1024 * 1024) {
            ArrayList<String> keep = new ArrayList<>();
            org.json.JSONArray a = BridgeCore.loadJsonLines(f, 500);
            for (int i = 0; i < a.length(); i++) keep.add(a.optJSONObject(i).toString());
            try (BufferedWriter w = new BufferedWriter(new FileWriter(f, false))) {
                for (String s : keep) { w.write(s); w.newLine(); }
            } catch (Exception ignored) {}
        }
    }
}

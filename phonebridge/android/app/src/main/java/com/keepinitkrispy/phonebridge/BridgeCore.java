package com.keepinitkrispy.phonebridge;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.ContentResolver;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.location.Location;
import android.location.LocationManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.provider.CallLog;
import android.provider.ContactsContract;
import android.provider.DocumentsContract;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;

public final class BridgeCore {
    static final String PREFS = "phonebridge";
    static final String KEY_TREE = "drive_tree";
    static final String KEY_LAST_SEQ = "last_command_seq";
    static final int JOB_ID = 42817;
    static final String STATE_NAME = "PhoneBridge-state.json";
    static final String COMMAND_URL = "https://raw.githubusercontent.com/keepinitkrispy/hello-world/phone-bridge/phonebridge/runtime/commands.json";

    private BridgeCore() {}

    public static void saveTreeUri(Context c, Uri uri) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_TREE, uri.toString()).apply();
    }

    static Uri getTreeUri(Context c) {
        String s = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_TREE, null);
        return s == null ? null : Uri.parse(s);
    }

    public static void schedulePeriodic(Context c) {
        JobScheduler scheduler = (JobScheduler) c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (scheduler == null) return;
        JobInfo info = new JobInfo.Builder(JOB_ID, new ComponentName(c, BridgeJobService.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(15 * 60 * 1000L)
                .setPersisted(true)
                .build();
        scheduler.schedule(info);
    }

    public static void syncNow(Context c, String reason) {
        Context app = c.getApplicationContext();
        new Thread(() -> {
            try { sync(app, reason); } catch (Throwable ignored) {}
        }, "PhoneBridgeSync").start();
    }

    static JSONObject sync(Context c, String reason) throws Exception {
        JSONObject command = fetchCommand();
        JSONObject actionResult = executeIfNew(c, command);
        JSONObject state = buildState(c, reason, command, actionResult);
        if (getTreeUri(c) != null) writeJsonToDrive(c, STATE_NAME, state.toString(2));
        return state;
    }

    private static JSONObject fetchCommand() {
        HttpURLConnection conn = null;
        try {
            URL u = new URL(COMMAND_URL + "?t=" + System.currentTimeMillis());
            conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(7000);
            conn.setReadTimeout(7000);
            conn.setRequestProperty("Cache-Control", "no-cache");
            if (conn.getResponseCode() != 200) return new JSONObject().put("seq", 0).put("action", "sync");
            BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            try { return new JSONObject().put("seq", 0).put("action", "sync").put("fetch_error", e.getClass().getSimpleName()); }
            catch (Exception ignored) { return new JSONObject(); }
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static JSONObject executeIfNew(Context c, JSONObject command) {
        JSONObject out = new JSONObject();
        try {
            long seq = command.optLong("seq", 0);
            SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            long last = p.getLong(KEY_LAST_SEQ, -1);
            String action = command.optString("action", "sync");
            out.put("seq", seq).put("action", action).put("executed", false);
            if (seq <= last) {
                out.put("status", "already_processed");
                return out;
            }

            switch (action) {
                case "sync":
                    out.put("executed", true).put("status", "ok");
                    break;
                case "volume": {
                    int percent = Math.max(0, Math.min(100, command.optInt("percent", 50)));
                    AudioManager am = (AudioManager) c.getSystemService(Context.AUDIO_SERVICE);
                    int max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                    int value = Math.round(max * (percent / 100f));
                    am.setStreamVolume(AudioManager.STREAM_MUSIC, value, 0);
                    out.put("executed", true).put("status", "ok").put("percent", percent);
                    break;
                }
                case "home":
                    out.put("executed", PhoneAccessibilityService.performBridgeAction("home"));
                    out.put("status", out.optBoolean("executed") ? "ok" : "accessibility_not_enabled");
                    break;
                case "back":
                    out.put("executed", PhoneAccessibilityService.performBridgeAction("back"));
                    out.put("status", out.optBoolean("executed") ? "ok" : "accessibility_not_enabled");
                    break;
                default:
                    out.put("status", "rejected_not_allowlisted");
            }
            p.edit().putLong(KEY_LAST_SEQ, seq).apply();
        } catch (Exception e) {
            try { out.put("status", "error").put("error", e.getClass().getSimpleName()); } catch (Exception ignored) {}
        }
        return out;
    }

    private static JSONObject buildState(Context c, String reason, JSONObject command, JSONObject actionResult) throws Exception {
        JSONObject root = new JSONObject();
        root.put("bridge_version", "0.1.0");
        root.put("updated_at", isoNow());
        root.put("reason", reason);
        root.put("privacy", "requested_categories_only");
        root.put("device", deviceInfo());
        root.put("battery", batteryInfo(c));
        root.put("capabilities", capabilities(c));
        root.put("command", command);
        root.put("action_result", actionResult);

        JSONArray include = command.optJSONArray("include");
        if (include == null) include = new JSONArray();
        for (int i = 0; i < include.length(); i++) {
            String item = include.optString(i, "");
            switch (item) {
                case "notifications": root.put("notifications", recentNotifications(c, 80)); break;
                case "location": root.put("location", locationInfo(c)); break;
                case "contacts": root.put("contacts", contactsInfo(c, 250)); break;
                case "calls": root.put("calls", callsInfo(c, 100)); break;
                case "sms": root.put("sms", smsInfo(c, 100)); break;
                case "apps": root.put("apps", appsInfo(c)); break;
                case "screen": root.put("screen", screenInfo(c)); break;
                default: break;
            }
        }
        return root;
    }

    private static JSONObject deviceInfo() throws Exception {
        return new JSONObject()
                .put("manufacturer", Build.MANUFACTURER)
                .put("model", Build.MODEL)
                .put("device", Build.DEVICE)
                .put("android_release", Build.VERSION.RELEASE)
                .put("sdk", Build.VERSION.SDK_INT);
    }

    private static JSONObject batteryInfo(Context c) throws Exception {
        BatteryManager bm = (BatteryManager) c.getSystemService(Context.BATTERY_SERVICE);
        int pct = bm == null ? -1 : bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        boolean charging = bm != null && bm.isCharging();
        return new JSONObject().put("percent", pct).put("charging", charging);
    }

    private static JSONObject capabilities(Context c) throws Exception {
        return new JSONObject()
                .put("drive_connected", getTreeUri(c) != null)
                .put("notification_access", hasNotificationAccess(c))
                .put("accessibility", hasAccessibility(c))
                .put("location", has(c, Manifest.permission.ACCESS_FINE_LOCATION) || has(c, Manifest.permission.ACCESS_COARSE_LOCATION))
                .put("contacts", has(c, Manifest.permission.READ_CONTACTS))
                .put("call_log", has(c, Manifest.permission.READ_CALL_LOG))
                .put("sms", has(c, Manifest.permission.READ_SMS))
                .put("installed_apps", true)
                .put("safe_remote_actions", new JSONArray().put("sync").put("volume").put("home").put("back"));
    }

    public static String humanStatus(Context c) {
        StringBuilder s = new StringBuilder();
        s.append(getTreeUri(c) != null ? "✓ Drive connected\n" : "○ Drive not connected\n");
        s.append(hasNotificationAccess(c) ? "✓ Notification access enabled\n" : "○ Notification access not enabled\n");
        s.append(hasAccessibility(c) ? "✓ Accessibility enabled (optional)\n" : "○ Accessibility off (optional)\n");
        s.append((has(c, Manifest.permission.ACCESS_FINE_LOCATION) || has(c, Manifest.permission.ACCESS_COARSE_LOCATION)) ? "✓ Location enabled (optional)\n" : "○ Location off (optional)\n");
        s.append(has(c, Manifest.permission.READ_CONTACTS) ? "✓ Contacts enabled (optional)\n" : "○ Contacts off (optional)\n");
        s.append(has(c, Manifest.permission.READ_CALL_LOG) ? "✓ Direct call log available\n" : "— Direct call log restricted by Android\n");
        s.append(has(c, Manifest.permission.READ_SMS) ? "✓ Direct SMS available" : "— Direct SMS restricted by Android");
        return s.toString();
    }

    static boolean has(Context c, String permission) {
        return c.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED;
    }

    static boolean hasNotificationAccess(Context c) {
        String enabled = Settings.Secure.getString(c.getContentResolver(), "enabled_notification_listeners");
        return enabled != null && enabled.contains(c.getPackageName());
    }

    static boolean hasAccessibility(Context c) {
        String enabled = Settings.Secure.getString(c.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return enabled != null && enabled.contains(c.getPackageName());
    }

    private static JSONObject locationInfo(Context c) throws Exception {
        JSONObject o = new JSONObject();
        if (!(has(c, Manifest.permission.ACCESS_FINE_LOCATION) || has(c, Manifest.permission.ACCESS_COARSE_LOCATION))) return o.put("available", false).put("reason", "permission_off");
        LocationManager lm = (LocationManager) c.getSystemService(Context.LOCATION_SERVICE);
        Location best = null;
        if (lm != null) {
            for (String provider : lm.getProviders(true)) {
                try {
                    Location l = lm.getLastKnownLocation(provider);
                    if (l != null && (best == null || l.getTime() > best.getTime())) best = l;
                } catch (SecurityException ignored) {}
            }
        }
        if (best == null) return o.put("available", false).put("reason", "no_last_location");
        return o.put("available", true).put("lat", best.getLatitude()).put("lon", best.getLongitude())
                .put("accuracy_m", best.getAccuracy()).put("time", best.getTime());
    }

    private static JSONArray recentNotifications(Context c, int max) {
        return loadJsonLines(new File(c.getFilesDir(), "notifications.jsonl"), max);
    }

    private static JSONObject screenInfo(Context c) throws Exception {
        String raw = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("last_screen", null);
        if (raw == null) return new JSONObject().put("available", false);
        try { return new JSONObject(raw).put("available", true); }
        catch (Exception e) { return new JSONObject().put("available", false); }
    }

    private static JSONArray contactsInfo(Context c, int max) {
        JSONArray arr = new JSONArray();
        if (!has(c, Manifest.permission.READ_CONTACTS)) return arr;
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                    new String[]{ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER},
                    null, null, ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC");
            int n = 0;
            while (cur != null && cur.moveToNext() && n++ < max) {
                arr.put(new JSONObject().put("name", cur.getString(0)).put("number", cur.getString(1)));
            }
        } catch (Exception ignored) {} finally { if (cur != null) cur.close(); }
        return arr;
    }

    private static JSONArray callsInfo(Context c, int max) {
        JSONArray arr = new JSONArray();
        if (!has(c, Manifest.permission.READ_CALL_LOG)) return arr;
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(CallLog.Calls.CONTENT_URI,
                    new String[]{CallLog.Calls.NUMBER, CallLog.Calls.CACHED_NAME, CallLog.Calls.TYPE, CallLog.Calls.DATE, CallLog.Calls.DURATION},
                    null, null, CallLog.Calls.DATE + " DESC");
            int n = 0;
            while (cur != null && cur.moveToNext() && n++ < max) {
                arr.put(new JSONObject().put("number", cur.getString(0)).put("name", cur.getString(1))
                        .put("type", cur.getInt(2)).put("date", cur.getLong(3)).put("duration_s", cur.getLong(4)));
            }
        } catch (Exception ignored) {} finally { if (cur != null) cur.close(); }
        return arr;
    }

    private static JSONArray smsInfo(Context c, int max) {
        JSONArray arr = new JSONArray();
        if (!has(c, Manifest.permission.READ_SMS)) return arr;
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(Uri.parse("content://sms"),
                    new String[]{"address", "date", "type", "body"}, null, null, "date DESC");
            int n = 0;
            while (cur != null && cur.moveToNext() && n++ < max) {
                arr.put(new JSONObject().put("address", cur.getString(0)).put("date", cur.getLong(1))
                        .put("type", cur.getInt(2)).put("body", cur.getString(3)));
            }
        } catch (Exception ignored) {} finally { if (cur != null) cur.close(); }
        return arr;
    }

    private static JSONArray appsInfo(Context c) {
        JSONArray arr = new JSONArray();
        try {
            PackageManager pm = c.getPackageManager();
            List<ApplicationInfo> apps = pm.getInstalledApplications(0);
            for (ApplicationInfo ai : apps) {
                arr.put(new JSONObject().put("package", ai.packageName).put("label", pm.getApplicationLabel(ai).toString()).put("enabled", ai.enabled));
            }
        } catch (Exception ignored) {}
        return arr;
    }

    static synchronized void writeJsonToDrive(Context c, String name, String content) throws Exception {
        Uri tree = getTreeUri(c);
        if (tree == null) throw new IllegalStateException("Drive not connected");
        ContentResolver r = c.getContentResolver();
        String parentId = DocumentsContract.getTreeDocumentId(tree);
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, parentId);
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId);
        Uri target = null;
        Cursor cur = r.query(children,
                new String[]{DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME},
                null, null, null);
        if (cur != null) {
            try {
                while (cur.moveToNext()) {
                    if (name.equals(cur.getString(1))) {
                        target = DocumentsContract.buildDocumentUriUsingTree(tree, cur.getString(0));
                        break;
                    }
                }
            } finally { cur.close(); }
        }
        if (target == null) target = DocumentsContract.createDocument(r, parent, "application/json", name);
        if (target == null) throw new IllegalStateException("Could not create Drive state file");
        OutputStream os;
        try { os = r.openOutputStream(target, "wt"); }
        catch (Exception e) { os = r.openOutputStream(target, "w"); }
        if (os == null) throw new IllegalStateException("Could not open Drive state file");
        try (OutputStream out = os) { out.write(content.getBytes(StandardCharsets.UTF_8)); }
    }

    static JSONArray loadJsonLines(File file, int max) {
        JSONArray arr = new JSONArray();
        if (!file.exists()) return arr;
        ArrayList<String> lines = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = br.readLine()) != null) {
                lines.add(line);
                if (lines.size() > max) lines.remove(0);
            }
            for (String s : lines) {
                try { arr.put(new JSONObject(s)); } catch (Exception ignored) {}
            }
        } catch (Exception ignored) {}
        return arr;
    }

    static String isoNow() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US);
        f.setTimeZone(TimeZone.getDefault());
        return f.format(new Date());
    }
}

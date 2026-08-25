package com.keepinitkrispy.phonebridge;

import android.Manifest;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final int PICK_DRIVE_FOLDER = 1001;
    private static final int OPTIONAL_PERMISSIONS = 1002;
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        BridgeCore.schedulePeriodic(this);
        BridgeCore.syncNow(this, "app-open");
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (status != null) status.setText(BridgeCore.humanStatus(this));
    }

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(42, 42, 42, 42);
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("Phone Bridge");
        title.setTextSize(30f);
        title.setTextColor(Color.WHITE);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Private by default. Raw phone data stays on-device unless a specific bridge request asks for it.\n\nBASIC SETUP = first two buttons only.");
        subtitle.setTextSize(16f);
        subtitle.setPadding(0, 16, 0, 26);
        root.addView(subtitle);

        status = new TextView(this);
        status.setTextSize(16f);
        status.setPadding(0, 0, 0, 24);
        root.addView(status);

        addButton(root, "1. Connect Google Drive folder", v -> chooseDriveFolder());
        addButton(root, "2. Enable Notification Access", v -> openNotificationAccess());
        addButton(root, "Optional: Location + Contacts", v -> requestOptionalPermissions());
        addButton(root, "Optional: Accessibility layer", v -> openAccessibilitySettings());
        addButton(root, "Test / Sync Now", v -> {
            BridgeCore.syncNow(this, "manual-test");
            Toast.makeText(this, "Bridge sync started", Toast.LENGTH_SHORT).show();
        });

        TextView note = new TextView(this);
        note.setText("What basic mode gives ChatGPT: notification history going forward (including missed-call/voicemail alerts), device/battery state, and a private Drive state file it can read. Optional access adds exact last-known location, contact lookup, visible-screen context, and safe Home/Back navigation. Android-restricted Call Log/SMS adapters are included but stay OFF unless the OS actually grants them.");
        note.setPadding(0, 28, 0, 10);
        note.setTextSize(14f);
        root.addView(note);

        setContentView(scroll);
    }

    private void addButton(LinearLayout root, String text, View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setOnClickListener(listener);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 8, 0, 8);
        root.addView(b, lp);
    }

    private void chooseDriveFolder() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION |
                Intent.FLAG_GRANT_WRITE_URI_PERMISSION |
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION |
                Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
        startActivityForResult(i, PICK_DRIVE_FOLDER);
    }

    private void openNotificationAccess() {
        try {
            Intent i = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS);
            i.putExtra(Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME,
                    new ComponentName(this, NotificationBridgeService.class).flattenToString());
            startActivity(i);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
        }
    }

    private void openAccessibilitySettings() {
        startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
    }

    private void requestOptionalPermissions() {
        requestPermissions(new String[]{
                Manifest.permission.ACCESS_FINE_LOCATION,
                Manifest.permission.ACCESS_COARSE_LOCATION,
                Manifest.permission.READ_CONTACTS
        }, OPTIONAL_PERMISSIONS);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_DRIVE_FOLDER && resultCode == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            int flags = data.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            try {
                getContentResolver().takePersistableUriPermission(uri, flags);
                BridgeCore.saveTreeUri(this, uri);
                BridgeCore.schedulePeriodic(this);
                BridgeCore.syncNow(this, "drive-connected");
                Toast.makeText(this, "Drive connected", Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                Toast.makeText(this, "Drive permission failed: " + e.getMessage(), Toast.LENGTH_LONG).show();
            }
        }
    }
}

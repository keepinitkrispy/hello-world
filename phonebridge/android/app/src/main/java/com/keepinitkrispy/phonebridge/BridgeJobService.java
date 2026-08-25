package com.keepinitkrispy.phonebridge;

import android.app.job.JobParameters;
import android.app.job.JobService;

public class BridgeJobService extends JobService {
    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try { BridgeCore.sync(this, "scheduled"); } catch (Throwable ignored) {}
            jobFinished(params, false);
        }, "PhoneBridgeJob").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}

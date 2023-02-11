"""
sharedMemoryAPI with player-synced methods

Inherit Python mapping of The Iron Wolf's rF2 Shared Memory Tools
and add access functions to it.
"""
# pylint: disable=invalid-name
import ctypes
import mmap
import time
import threading
import copy
import platform

try:
    from . import rF2data
except ImportError:  # standalone, not package
    import rF2data


class SimInfoSync():
    """
    API for rF2 shared memory

    Player-Synced data.
    """

    def __init__(self, input_pid=""):
        self.players_index = 99
        self.data_updating = False
        self._input_pid = input_pid

        self._rf2_tele = None  # map shared memory
        self._rf2_scor = None
        self._rf2_ext = None
        self._rf2_ffb = None

        self.Rf2Tele = None  # raw data
        self.Rf2Scor = None
        self.Rf2Ext = None
        self.Rf2Ffb = None

        self.DefTele = None  # default copy of raw data
        self.DefScor = None
        self.DefExt = None
        self.DefFfb = None

        self.LastTele = None  # synced copy of raw data
        self.LastScor = None
        self.LastExt = None
        self.LastFfb = None

        self.start_mmap()
        self.set_default_mmap()
        print("sharedmemory mapping started")

    def start_mmap(self):
        """ Start memory mapping """
        if platform.system() == "Windows":
            self._rf2_tele = mmap.mmap(0, ctypes.sizeof(rF2data.rF2Telemetry),
                                       f"$rFactor2SMMP_Telemetry${self._input_pid}")
            self._rf2_scor = mmap.mmap(0, ctypes.sizeof(rF2data.rF2Scoring),
                                       f"$rFactor2SMMP_Scoring${self._input_pid}")
            self._rf2_ext = mmap.mmap(0, ctypes.sizeof(rF2data.rF2Extended),
                                      f"$rFactor2SMMP_Extended${self._input_pid}")
            self._rf2_ffb = mmap.mmap(0, ctypes.sizeof(rF2data.rF2ForceFeedback),
                                      "$rFactor2SMMP_ForceFeedback$")
        else:
            tele_file = open("/dev/shm/$rFactor2SMMP_Telemetry$", "r+")
            self._rf2_tele = mmap.mmap(tele_file.fileno(), ctypes.sizeof(rF2data.rF2Telemetry))
            scor_file = open("/dev/shm/$rFactor2SMMP_Scoring$", "r+")
            self._rf2_scor = mmap.mmap(scor_file.fileno(), ctypes.sizeof(rF2data.rF2Scoring))
            ext_file = open("/dev/shm/$rFactor2SMMP_Extended$", "r+")
            self._rf2_ext = mmap.mmap(ext_file.fileno(), ctypes.sizeof(rF2data.rF2Extended))
            ffb_file = open("/dev/shm/$rFactor2SMMP_ForceFeedback$", "r+")
            self._rf2_ffb = mmap.mmap(ffb_file.fileno(), ctypes.sizeof(rF2data.rF2ForceFeedback))

        self.Rf2Tele = rF2data.rF2Telemetry.from_buffer(self._rf2_tele)
        self.Rf2Scor = rF2data.rF2Scoring.from_buffer(self._rf2_scor)
        self.Rf2Ext = rF2data.rF2Extended.from_buffer(self._rf2_ext)
        self.Rf2Ffb = rF2data.rF2ForceFeedback.from_buffer(self._rf2_ffb)

        self.DefTele = copy.deepcopy(self.Rf2Tele)
        self.DefScor = copy.deepcopy(self.Rf2Scor)
        self.DefExt = copy.deepcopy(self.Rf2Ext)
        self.DefFfb = copy.deepcopy(self.Rf2Ffb)

    def set_default_mmap(self):
        """ Set default memory mapping data """
        self.LastTele = copy.deepcopy(self.DefTele)
        self.LastScor = copy.deepcopy(self.DefScor)
        self.LastExt = copy.deepcopy(self.DefExt)
        self.LastFfb = copy.deepcopy(self.DefFfb)

    def reset_mmap(self):
        """ Reset memory mapping """
        self.close()  # close mmap first
        self.start_mmap()

    def close(self):
        """ Close memory mapping """
        # This didn't help with the errors
        try:
            # Unassign those objects first
            self.Rf2Tele = None
            self.Rf2Scor = None
            self.Rf2Ext = None
            self.Rf2Ffb = None
            # Close shared memory mapping
            self._rf2_tele.close()
            self._rf2_scor.close()
            self._rf2_ext.close()
            self._rf2_ffb.close()
            print("sharedmemory mapping closed")
        except BufferError:  # "cannot close exported pointers exist"
            print("BufferError")
            pass

    ###########################################################
    # Sync data for local player

    def __playerVerified(self, input_data):
        """ Check player index number on one same data piece """
        for _player in range(128):  # max 128 players supported by API
            # Use 1 to avoid reading incorrect value
            if input_data.mVehicles[_player].mIsPlayer == 1:
                self.players_index = _player
                return True
        return False  # return false if failed to find player index

    @staticmethod
    def dataVerified(input_data):
        """ Verify data """
        return input_data.mVersionUpdateEnd == input_data.mVersionUpdateBegin

    def __infoUpdate(self):
        """ Update synced player data """
        players_mid = 0          # player mID
        last_version_update = 0  # store last data version update
        re_version_update = 0    # store restarted data version update
        mmap_restarted = True    # whether has restarted memory mapping
        check_counter = 0        # counter for data version update check
        restore_counter = 71      # counter for restoring mmap data to default

        while self.data_updating:
            data_scor = copy.deepcopy(self.Rf2Scor)  # use deepcopy to avoid data interruption
            data_tele = copy.deepcopy(self.Rf2Tele)
            self.LastExt = copy.deepcopy(self.Rf2Ext)
            self.LastFfb = copy.deepcopy(self.Rf2Ffb)

            # Only update if data verified and player index found
            if self.dataVerified(data_scor) and self.__playerVerified(data_scor):
                self.LastScor = copy.deepcopy(data_scor)  # synced scoring
                players_mid = self.LastScor.mVehicles[self.players_index].mID  # update player mID

                # Only update if data verified and player mID matches
                if (self.dataVerified(data_tele) and
                    data_tele.mVehicles[self.players_index].mID == players_mid):
                    self.LastTele = copy.deepcopy(data_tele)  # synced telemetry

            # Start checking data version update status
            check_counter += 1

            if check_counter > 70:  # active after around 1 seconds
                if (not mmap_restarted and last_version_update > 0
                    and last_version_update == self.LastScor.mVersionUpdateEnd):
                    self.reset_mmap()
                    mmap_restarted = True
                    re_version_update = self.LastScor.mVersionUpdateEnd
                    print(f"sharedmemory mapping restarted - version:{last_version_update}")
                last_version_update = self.LastScor.mVersionUpdateEnd
                check_counter = 0  # reset counter

            if mmap_restarted:
                if re_version_update != self.LastScor.mVersionUpdateEnd:
                    mmap_restarted = False
                    restore_counter = 0  # reset counter
                elif restore_counter < 71:
                    restore_counter += 1

            if restore_counter == 70:  # active after around 1 seconds
                self.set_default_mmap()
                print("sharedmemory mapping data reset to default")

            #print(f"c1:{check_counter:03.0f} "
            #      f"c2:{restore_counter:03.0f} "
            #      f"now:{self.LastScor.mVersionUpdateEnd:07.0f} "
            #      f"last:{last_version_update:07.0f} "
            #      f"re:{re_version_update:07.0f} "
            #      f"{mmap_restarted}", end="\r")

            time.sleep(0.01)

        print("sharedmemory synced player data updating thread stopped")

    def startUpdating(self):
        """ Start data updating thread """
        self.data_updating = True
        index_thread = threading.Thread(target=self.__infoUpdate)
        index_thread.daemon=True
        index_thread.start()
        print("sharedmemory synced player data updating thread started")

    def stopUpdating(self):
        """ Stop data updating thread """
        self.data_updating = False
        time.sleep(0.2)

    def syncedVehicleTelemetry(self):
        """ Get the variable for the player's vehicle """
        return self.LastTele.mVehicles[self.players_index]

    def syncedVehicleScoring(self):
        """ Get the variable for the player's vehicle """
        return self.LastScor.mVehicles[self.players_index]

    ###########################################################

    def __del__(self):
        self.close()

if __name__ == '__main__':
    # Example usage
    info = SimInfoSync()
    info.startUpdating()  # start Shared Memory updating thread
    version = info.LastExt.mVersion
    v = bytes(version).partition(b'\0')[0].decode().rstrip()
    clutch = info.LastTele.mVehicles[0].mUnfilteredClutch # 1.0 clutch down, 0 clutch up
    gear   = info.LastTele.mVehicles[0].mGear  # -1 to 6
    print(f"Map version: {v}\n"
          f"Gear: {gear}, Clutch position: {clutch}")

    info.stopUpdating()  # stop sharedmemory synced player data updating thread

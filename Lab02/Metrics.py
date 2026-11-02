class Metrics:

    def __init__(self, standPositions, warmup: int = 0, endTime: int = 0):

        # finestra di misura [warmup, endTime]: tutto ciò che accade prima di
        # warmup (transitorio) o dopo endTime viene ignorato
        self.warmup = warmup
        self.endTime = endTime

        # --- contatori ---
        self.nUsers = 0          # clienti generati
        self.nRide = 0           # corse completate (conteggiate all'arrivo a destinazione)
        self.nUserInLoco = 0     # clienti in loco partiti dallo stand
        self.nUserOnLine = 0     # clienti online raggiunti dal taxi
        self.nRedistributions = 0  # taxi spostati da uno stand a un altro per coprire una coda

        # --- accumulatori di tempo ---
        self.waitedInLocoAcc = 0
        self.waitedOnLineAcc = 0
        self.rideTimeAcc = 0          # taxi con cliente a bordo
        self.timeBackToStandAcc = 0   # taxi vuoto verso uno stand
        self.timeToUserAcc = 0        # taxi vuoto verso un cliente

        # --- integrali nel tempo (aggiornati da update) ---
        self.lastTime = 0
        self.onLineQueueAcc = 0
        self.standPositions = list(standPositions)
        self.idleTaxiAccPerStand = {pos: 0 for pos in self.standPositions}
        self.queueAccPerStand = {pos: 0 for pos in self.standPositions}
        self.maxQueuePerStand = {pos: 0 for pos in self.standPositions}

        # --- clienti in loco per stand ---
        self.nUserInLocoPerStand = {pos: 0 for pos in self.standPositions}
        self.waitedInLocoAccPerStand = {pos: 0 for pos in self.standPositions}


    # ------------------------------------------------------------------
    # Da chiamare a ogni evento, PRIMA di processarlo
    # ------------------------------------------------------------------
    def update(self, time: int, taxiStands) -> None:
        # lo stato attuale vale nell'intervallo [lastTime, time]: si integra
        # solo la parte che cade dentro la finestra di misura
        start = max(self.lastTime, self.warmup)
        end = min(time, self.endTime)
        dt = max(0, end - start)

        for pos in self.standPositions:
            stand = taxiStands.stands[pos]
            qLen = len(stand.userQueue)

            self.idleTaxiAccPerStand[pos] += stand.nTaxi * dt
            self.queueAccPerStand[pos] += qLen * dt
            if dt > 0 and qLen > self.maxQueuePerStand[pos]:
                self.maxQueuePerStand[pos] = qLen

        self.onLineQueueAcc += len(taxiStands.onlineQueue) * dt
        self.lastTime = time


    def _inWindow(self, time: int) -> bool:
        return self.warmup <= time <= self.endTime


    def _overlap(self, start: int, duration: int) -> int:
        # parte di un intervallo [start, start+duration] dentro la finestra di misura
        return max(0, min(start + duration, self.endTime) - max(start, self.warmup))


    # ------------------------------------------------------------------
    # Contatori e tempi
    # ------------------------------------------------------------------
    def incrementUserCounter(self, time: int) -> None:
        if self._inWindow(time):
            self.nUsers += 1


    def incrementRideCounter(self, time: int) -> None:
        # da chiamare quando la corsa FINISCE
        if self._inWindow(time):
            self.nRide += 1


    def incrementRedistribution(self, time: int) -> None:
        if self._inWindow(time):
            self.nRedistributions += 1


    def recordInLocoWait(self, standLocation: tuple[int, int], waitedTime: int, time: int) -> None:
        # quando un cliente in loco parte dallo stand
        if not self._inWindow(time):
            return
        self.nUserInLoco += 1
        self.waitedInLocoAcc += waitedTime
        self.nUserInLocoPerStand[standLocation] += 1
        self.waitedInLocoAccPerStand[standLocation] += waitedTime


    def recordOnLineWait(self, waitedTime: int, time: int) -> None:
        # quando il taxi raggiunge un cliente online
        if not self._inWindow(time):
            return
        self.nUserOnLine += 1
        self.waitedOnLineAcc += waitedTime


    # i tempi di viaggio si registrano alla partenza del tratto, ma contano solo
    # per la parte che cade nella finestra di misura (niente sforamenti oltre endTime)
    def incrementRideTimeAcc(self, start: int, duration: int) -> None:
        self.rideTimeAcc += self._overlap(start, duration)


    def incrementTimeBackToStand(self, start: int, duration: int) -> None:
        self.timeBackToStandAcc += self._overlap(start, duration)


    def incrementTimeToUser(self, start: int, duration: int) -> None:
        self.timeToUserAcc += self._overlap(start, duration)


    # ------------------------------------------------------------------
    # Risultati finali
    # ------------------------------------------------------------------
    def globalReport(self, nTaxi: int, taxiStands=None) -> dict:
        endTime = self.endTime - self.warmup      # durata della finestra di misura
        idleAcc = sum(self.idleTaxiAccPerStand.values())
        totalTaxiTime = endTime * nTaxi

        return {
            "nUsers": self.nUsers,
            "nRide": self.nRide,
            "nRedistributions": self.nRedistributions,
            "avgWaitInLoco": self.waitedInLocoAcc / self.nUserInLoco if self.nUserInLoco > 0 else 0.0,
            "avgWaitOnLine": self.waitedOnLineAcc / self.nUserOnLine if self.nUserOnLine > 0 else 0.0,
            "avgQueueInLoco": sum(self.queueAccPerStand.values()) / endTime,
            "avgQueueOnLine": self.onLineQueueAcc / endTime,
            # frazione del tempo dei taxi in ciascuno stato (somma ~ 1)
            "fracRide": self.rideTimeAcc / totalTaxiTime,
            "fracToUser": self.timeToUserAcc / totalTaxiTime,
            "fracBackToStand": self.timeBackToStandAcc / totalTaxiTime,
            "fracIdle": idleAcc / totalTaxiTime,
            # clienti ancora in attesa a fine simulazione (le loro attese NON sono
            # nelle medie: il loro numero dice quanto è forte il bias di troncamento)
            "nStillWaitingInLoco": taxiStands.getTotalInLoco() if taxiStands else 0,
            "nStillWaitingOnLine": taxiStands.getTotalOnline() if taxiStands else 0,
        }


    def standReport(self) -> dict:
        endTime = self.endTime - self.warmup
        report = {}
        for pos in self.standPositions:
            n = self.nUserInLocoPerStand[pos]
            report[pos] = {
                "avgIdleTaxi": self.idleTaxiAccPerStand[pos] / endTime,
                "avgQueue": self.queueAccPerStand[pos] / endTime,
                "maxQueue": self.maxQueuePerStand[pos],
                "nUserInLoco": n,
                "avgWaitInLoco": self.waitedInLocoAccPerStand[pos] / n if n > 0 else 0.0,
            }
        return report
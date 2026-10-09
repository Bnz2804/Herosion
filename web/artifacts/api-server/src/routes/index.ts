import { Router, type IRouter } from "express";
import healthRouter from "./health";
import workbenchRouter from "./workbench";
import plotsRouter from "./plots";
import advisoriesRouter from "./advisories";
import auditRouter from "./audit";

const router: IRouter = Router();

router.use(healthRouter);
router.use(workbenchRouter);
router.use(plotsRouter);
router.use(advisoriesRouter);
router.use(auditRouter);

export default router;

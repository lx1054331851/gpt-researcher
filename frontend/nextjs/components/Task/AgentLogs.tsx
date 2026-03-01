import { useTranslations } from "next-intl";

export default function AgentLogs({agentLogs}:any){  
  const t = useTranslations();

  const renderAgentLogs = (agentLogs:any)=>{
    return agentLogs && agentLogs.map((agentLog:any, index:number)=>{
      return (<div key={index}>{agentLog.output}</div>)
    })
  }

  return (
    <div className="margin-div">
        <h2>{t("report.agentWork")}</h2>
        <div id="output">
          {renderAgentLogs(agentLogs)}
        </div>
    </div>
  );
}
